# frozen_string_literal: true

# No Rails bootstrap for probes. Only the web init is permitted to run migrations.
require 'json'
require 'timeout'

module MastodonStartup
  class NotReady < StandardError; end
  LOCK = 901_746_283
  MIGRATION_COMMAND = %w[bundle exec rake db:migrate].freeze

  def self.log(stage, result, started, exit_code: nil)
    puts JSON.generate(event: 'mastodon_startup', stage: stage, result: result,
                       duration_seconds: (now - started).round(6), exit_code: exit_code)
  end

  def self.now
    Process.clock_gettime(Process::CLOCK_MONOTONIC)
  end

  def self.postgres
    require 'pg'
    PG.connect(host: ENV.fetch('DB_HOST'), port: ENV.fetch('DB_PORT', '5432'),
               user: ENV.fetch('DB_USER'), password: ENV.fetch('DB_PASS'),
               dbname: ENV.fetch('DB_NAME'), connect_timeout: 4,
               options: '-c default_transaction_read_only=on -c statement_timeout=4000')
  end

  def self.valkey
    require 'redis'
    client = Redis.new(host: ENV.fetch('REDIS_HOST'), port: ENV.fetch('REDIS_PORT', '6379'),
                       password: ENV.fetch('REDIS_PASSWORD'), connect_timeout: 4,
                       read_timeout: 4, write_timeout: 4, reconnect_attempts: 0)
    raise NotReady unless client.ping == 'PONG'
  ensure
    client&.close
  end

  def self.dependencies
    connection = postgres
    raise NotReady unless connection.exec('SELECT 1 AS ready').first.fetch('ready') == '1'
    valkey
  ensure
    connection&.close
  end

  def self.expected_versions
    files = Dir['db/migrate/[0-9]*.rb', 'db/post_migrate/[0-9]*.rb']
    versions = files.map { |file| File.basename(file).split('_', 2).first }
    raise NotReady if versions.empty? || versions.any? { |v| !v.match?(/\A[0-9]+\z/) }
    raise NotReady unless versions.uniq.length == versions.length

    versions
  end

  def self.schema_versions(connection)
    # Missing/uninitialized production DB fails closed; never db:prepare/create/seeds.
    versions = Timeout.timeout(5) do
      connection.exec('SELECT version FROM schema_migrations').map { |row| row.fetch('version') }
    end
    raise NotReady if versions.empty?

    versions
  end

  def self.pending?(connection)
    !(expected_versions - schema_versions(connection)).empty?
  end

  def self.schema
    connection = postgres
    acquired = connection.exec("SELECT pg_try_advisory_lock_shared(#{LOCK}) AS acquired").first.fetch('acquired') == 't'
    raise NotReady unless acquired
    raise NotReady if pending?(connection)

    valkey
  ensure
    # Closing a session also releases its advisory locks, including error paths.
    connection&.close
  end

  def self.wait(stage, budget: 300, interval: 5, attempt_timeout: 5)
    raise ArgumentError unless %w[dependencies schema].include?(stage)

    started = now
    deadline = started + budget
    loop do
      remaining = deadline - now
      break if remaining <= 0
      begin
        Timeout.timeout([attempt_timeout, remaining].min) { public_send(stage) }
        log(stage, 'ready', started)
        return true
      rescue StandardError, LoadError
        log(stage, 'waiting', started) # Driver exceptions may contain credentials.
      end
      sleep [interval, [deadline - now, 0].max].min
    end
    log(stage, 'timeout', started)
    false
  end

  def self.stop_child(pid)
    return unless pid

    Process.kill('TERM', -pid)
    deadline = now + 5
    loop do
      return if Process.waitpid(pid, Process::WNOHANG)
      break if now >= deadline
      sleep 0.1
    end
    Process.kill('KILL', -pid)
    Process.waitpid(pid)
  rescue Errno::ESRCH, Errno::ECHILD
    nil
  end

  def self.run_migration(connection, deadline)
    # Fixed argv, no shell and no default raw migration/driver output.
    started = now
    pid = Process.spawn({ 'SKIP_POST_DEPLOYMENT_MIGRATIONS' => nil }, *MIGRATION_COMMAND,
                        pgroup: true, out: File::NULL, err: File::NULL)
    loop do
      if Process.waitpid(pid, Process::WNOHANG)
        status = $?
        pid = nil
        log('migration_process', status.success? ? 'complete' : 'failed', started, exit_code: status.exitstatus)
        raise NotReady unless status.success?
        return
      end
      raise NotReady if now >= deadline
      # A lost coordinator lock/session must not leave an unobserved writer running.
      Timeout.timeout(5) { connection.exec('SELECT 1 AS ready') }
      sleep 1
    end
  ensure
    stop_child(pid)
  end

  def self.migrate(budget: 1800, interval: 5)
    raise ArgumentError unless ENV['MASTODON_MIGRATION_OWNER'] == 'web-init'

    started = now
    deadline = started + budget
    connection = Timeout.timeout(5) { postgres }
    loop do
      acquired = Timeout.timeout(5) do
        connection.exec("SELECT pg_try_advisory_lock(#{LOCK}) AS acquired").first.fetch('acquired') == 't'
      end
      break if acquired
      raise NotReady if now >= deadline
      log('migration_lock', 'waiting', started)
      sleep [interval, [deadline - now, 0].max].min
    end
    schema_versions(connection) # Refuse an empty or missing production schema.
    if pending?(connection)
      # Initial adoption must be no-op; future writes need a reviewed maintenance commit.
      raise NotReady unless ENV['MASTODON_ALLOW_PENDING_MIGRATIONS'] == 'true'
      log('migrations', 'running', started)
      run_migration(connection, deadline)
      raise NotReady if pending?(connection)
      log('migrations', 'complete', started)
    else
      log('migrations', 'already_applied', started)
    end
    true
  ensure
    connection&.close
  end

  def self.main(mode)
    case mode
    when 'dependencies' then wait('dependencies')
    when 'schema' then wait('schema', budget: 1800)
    when 'migrate'
      wait('dependencies') && migrate
    else raise ArgumentError
    end
  end
end

if $PROGRAM_NAME == __FILE__
  $stdout.sync = true
  Signal.trap('TERM') { raise Interrupt }
  Signal.trap('INT') { raise Interrupt }
  begin
    success = MastodonStartup.main(ARGV.fetch(0))
  rescue StandardError, LoadError, Interrupt
    puts JSON.generate(event: 'mastodon_startup', result: 'blocked')
    success = false
  end
  exit(success ? 0 : 1)
end
