#!/usr/bin/with-contenv bash
if [[ ! -v $PGID ]]; then
  PGID=1000
fi

if [[ ! -v $PUID ]]; then
  PUID=1000
fi

groupmod -g "$PGID" users
useradd -u "$PUID" -U -d /config -s /bin/false abc
usermod -G users abc

chown -R abc:users /config /app /sonarr_root /logs

chmod a+x\
/app/sonarr_youtubedl.py \
/app/run.sh \
/app/utils.py \
/app/config.yml.template

cd /app || exit

exec \
    s6-setuidgid abc python -u "/app/sonarr_youtubedl.py"