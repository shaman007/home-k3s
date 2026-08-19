# Spotify statistics locally saved stats

* Source: [github.com/Yooooomi/your_spotify](https://github.com/Yooooomi/your_spotify)
* I had to use 2 ingresses since there is a redirect to the servers's address
FerretDB 2.7.0 and PostgreSQL 17 with the DocumentDB extension are the active
database. The retired MongoDB rollback workload and volume were removed after
the migration was validated; completed Longhorn backups remain available for
disaster recovery.

`FERRETDB_USERNAME` and `FERRETDB_PASSWORD` are stored in the existing
`kv/spotify` OpenBao secret. Use a username that is valid as a PostgreSQL role
name and a URL-safe password.

Your Spotify 1.20.0 logs its database connection URI during startup. Treat
server logs as sensitive and always redact the URI user-info section when
sharing diagnostic output. Rotate the FerretDB role password if an unredacted
startup log is disclosed.
