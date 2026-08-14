# Spotify statistics locally saved stats

* Source: [github.com/Yooooomi/your_spotify](https://github.com/Yooooomi/your_spotify)
* I had to use 2 ingresses since there is a redirect to the servers's address
* MongoDB remains the active database while the FerretDB migration is staged.

## MongoDB to FerretDB migration

FerretDB 2.7.0 and PostgreSQL 17 with the DocumentDB extension are deployed in
parallel with MongoDB. The `mongodb` Service continues to select the original
MongoDB StatefulSet until the migration is validated.

Before syncing these manifests, add `FERRETDB_USERNAME` and
`FERRETDB_PASSWORD` to the existing `kv/spotify` OpenBao secret. Use a username
that is valid as a PostgreSQL role name and a URL-safe password.

Migration procedure:

1. Sync the application and wait for `ferretdb-postgres` and `ferretdb` to be
   ready.
2. Take a Longhorn snapshot/backup of `mongo-lh`.
3. Scale the `server` Deployment to zero for the maintenance window.
4. Create the skipped Job from `tools/job-migrate-mongodb-to-ferretdb.yaml` and
   wait for it to complete. It dumps, restores with `--drop`, and compares every
   collection's document count.
5. Change `MONGO_ENDPOINT` in `deployment-server.yaml` to reference the
   `mongodb-url` key from `ferretdb-credentials`, and change the selector in
   `service-mongodb.yaml` from `app: mongodb` to `app: ferretdb`.
6. Sync, restore the `server` Deployment to one replica, and validate login,
   refresh/import, API queries, indexes, and logs.
7. Retain `stateful-set-mongodb.yaml` and `mongo-lh` for rollback. Roll back by
   restoring the old endpoint and Service selector before starting the server.

Do not run the migration while the server is writing to MongoDB. Re-running the
Job replaces the target collections because `mongorestore --drop` is used.
