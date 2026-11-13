# frozen_string_literal: true

# Run under the application's Bundler environment; never load Rails or migrations.
require 'json'
require 'net/http'
require 'timeout'

module StartupGate
  class NotReady < StandardError; end

  def self.postgres
    require 'pg'
    connection = PG.connect(
      host: ENV.fetch('DATABASE_HOST'), port: ENV.fetch('DATABASE_PORT'),
      user: ENV.fetch('DATABASE_USERNAME'), password: ENV.fetch('DATABASE_PASSWORD'),
      dbname: ENV.fetch('DATABASE_NAME'), connect_timeout: 5,
      options: '-c default_transaction_read_only=on -c statement_timeout=4000'
    )
    raise NotReady unless connection.exec('SELECT 1').getvalue(0, 0) == '1'
  ensure
    connection&.close
  end

  def self.valkey
    require 'redis'
    client = Redis.new(url: ENV.fetch('REDIS_URL'), connect_timeout: 5,
                       read_timeout: 5, write_timeout: 5, reconnect_attempts: 0)
    raise NotReady unless client.ping == 'PONG'
  ensure
    client&.close
  end

  def self.web
    # Bypass proxy environment variables and never follow redirects.
    http = Net::HTTP.new('127.0.0.1', 3000, nil)
    http.open_timeout = 5
    http.read_timeout = 5
    request = Net::HTTP::Get.new('/api/v1/ready')
    request['Host'] = 'localhost'
    response = http.request(request)
    raise NotReady unless response.code == '200' && JSON.parse(response.body)['status'] == 'ok'
  end

  def self.wait(mode, budget: 300, interval: 5, attempt_timeout: 5)
    checks = { 'dependencies' => %i[postgres valkey], 'web' => %i[web] }.fetch(mode)
    deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + budget
    loop do
      ready = true
      checks.each do |stage|
        remaining = deadline - Process.clock_gettime(Process::CLOCK_MONOTONIC)
        return 1 if remaining <= 0

        started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
        result = 'ready'
        begin
          Timeout.timeout([attempt_timeout, remaining].min) { public_send(stage) }
        rescue StandardError, LoadError
          # Deliberately discard exception class/text: drivers can include credentials.
          ready = false
          result = 'not_ready'
        end
        puts JSON.generate(event: 'startup_gate', stage: stage, result: result,
                           duration_seconds: (Process.clock_gettime(Process::CLOCK_MONOTONIC) - started).round(6))
      end
      return 0 if ready

      remaining = deadline - Process.clock_gettime(Process::CLOCK_MONOTONIC)
      return 1 if remaining <= 0

      sleep [interval, remaining].min
    end
  end
end

if $PROGRAM_NAME == __FILE__
  $stdout.sync = true
  begin
    result = StartupGate.wait(ARGV.fetch(0))
  rescue StandardError, LoadError
    puts JSON.generate(event: 'startup_gate', result: 'configuration_error')
    result = 1
  end
  puts JSON.generate(event: 'startup_gate', result: result.zero? ? 'complete' : 'blocked')
  exit result
end
