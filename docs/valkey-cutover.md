# Valkey cutover

WordPress, Nextcloud, Dawarich, and Mastodon now use repo-native Valkey
StatefulSets. Their old Redis data is intentionally not imported.

## Before publishing this change

Argo CD prunes the four old Redis Applications automatically after this change
reaches `main`. Complete these checks before pushing it.

1. Put Mastodon into a maintenance window so web and streaming processes stop
   enqueueing new Sidekiq work.
2. Leave the Sidekiq worker running until its active queue count and busy count
   are both zero. Check from the Sidekiq pod:

   ```sh
   bundle exec rails runner 'puts({queued: Sidekiq::Queue.all.sum(&:size), busy: Sidekiq::Workers.new.size}.inspect)'
   ```

3. Put Dawarich into a maintenance window and drain its Sidekiq queues using the
   same Rails runner check.
4. Confirm no important jobs remain in `Sidekiq::RetrySet` or
   `Sidekiq::ScheduledSet`. These sets should be reviewed rather than silently
   discarded.
5. Push the GitOps change and wait for all four Valkey pods to become Ready.
6. Verify WordPress login/session handling, Nextcloud locking, Dawarich job
   processing, Mastodon web/streaming/Sidekiq, and all Valkey exporter targets.

The former Redis PVCs are retained by their StatefulSets. Remove those PVCs
only after the applications have run successfully on Valkey and rollback is no
longer required.
