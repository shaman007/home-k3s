# !!! OBSOLETE !!!
# CCTV that does everyting I need without Foscam applicatio

I have a Foscam dome camera that is cheap and decently build. At first I thought that Foscam application is required, however, the camera supports RTSP stream and can upload videos on motion detection to the FTP server.

* web page with mjpeg (with sound!) that just shows the stream is no that trivial to create. I use lighthppd that just shows ```ffmpeg -rtsp_transport tcp -i "rtsp://$USER:$PASSWORD@192.168.1.20:88/videoMain" -c:v mjpeg -q:v 1 -f mpjpeg -an -``` output. Native app is required to configure the user and password.
* FTP server in the K8S (k3s) is not trivial due to you have to list all ports you need for the FTP server. Amount of ports is equal to the amount of clients you'll have, I need just 2.
* Vs-ftpd in container Dockerfile exists,  https://github.com/fauria/docker-vsftpd.git, but it's needed to be built for the ARM64.
