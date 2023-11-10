#/bin/sh

apt-get update
apt -y install mysql-client
/usr/bin/mysqldump --defaults-extra-file=/nextcloud/my.cnf -u root -h mysql --all-databases --single-transaction --quick | gzip > /nextcloud/backup-`date +%s%N`.sql.gz
