FROM python:3.9-buster
LABEL maintainer="William Brown <Will@WillJBrown.com>"

# Update and install ffmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg s6

# Copy and install requirements
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

# create abc user so root isn't used
RUN \
    # create some files / folders
	mkdir -p /config /app /sonarr_root /logs && \
	touch /var/lock/sonarr_youtube.lock

# add volumes
VOLUME /config
VOLUME /sonarr_root
VOLUME /logs

# add local files
COPY app/ /app

# update file permissions
RUN \
    chmod a+x \
    /app/sonarr_youtubedl.py \
    /app/run.sh \
    /app/utils.py \
    /app/config.yml.template

# ENV setup
ENV CONFIGPATH /config/config.yml

CMD [ "bash", "/app/run.sh" ]
