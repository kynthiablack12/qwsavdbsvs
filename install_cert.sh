#!/system/bin/sh
set -x
mkdir -p /data/mitm/cacerts
cp -r /system/etc/security/cacerts/. /data/mitm/cacerts/
cp /data/local/tmp/c8750f0d.0 /data/mitm/cacerts/c8750f0d.0
chmod 644 /data/mitm/cacerts/*
chown root:root /data/mitm/cacerts/*
mount -o bind /data/mitm/cacerts /system/etc/security/cacerts
ls -la /system/etc/security/cacerts/c8750f0d.0
