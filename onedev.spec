%undefine _debugsource_packages
# For the moment, onedev bundles a slew of Java libs.
# No need to require system versions of them.
%global __requires_exclude jmod(.*)

Name: onedev
Version: 9.0.5
Release: 1
# List of available releases:
# https://code.onedev.io/onedev/server/~builds?query=%22Job%22+is+%22Release%22
Source0: https://code.onedev.io/~downloads/projects/160/builds/4039/artifacts/onedev-%{version}.tar.gz
# OneDev comes with a prebuilt version of Tanuki Wrapper
# https://wrapper.tanukisoftware.com/doc/english/home.html
# We replace it with a version we build from source.
Source1: https://sourceforge.net/projects/wrapper/files/wrapper_src/Wrapper_3.5.54_20230512/wrapper_3.5.54_src.tar.gz/download#/wrapper-3.5.54.tar.gz
Source10: onedev.sysusers
Summary: A git hosting tool, similar to gitlab or github
URL: https://github.com/onedev/onedev
License: MIT
Group: Servers

BuildRequires: jdk-current

Requires: curl
Requires: git
Requires: jre-current
# https://code.onedev.io/onedev/server/~issues/903
Requires: fontconfig
Requires: fonts-ttf-dejavu

# For TanukiWrapper
BuildRequires: ant
BuildRequires: pkgconfig(cunit)
BuildRequires: pkgconfig(ncursesw)

%description
A git hosting tool, similar to gitlab or github

%prep
%autosetup -p1 -a 1

%build
. /etc/profile.d/90java.sh
JAVA_VERSION=$(java -version 2>&1|head -n1 |cut -d' ' -f3 |sed -e 's,\",,g;s,-.*,,')
JAVA_MAJOR=$(echo ${JAVA_VERSION} |cut -d. -f1)

%ifarch %{ix86} %{arm} %{riscv32}
BITS=32
%else
BITS=64
%endif

cd wrapper_*_src
ant -f build.xml -Dbits=$BITS -Dant.java.version=$JAVA_VERSION -Djavac.target.version=$JAVA_MAJOR
cd ..
rm -f boot/wrapper-* boot/libwrapper-*.{so,sl,dylib,jnilib}
%ifarch %{x86_64}
mv wrapper_*_src/bin/wrapper boot/wrapper-%{_target_os}-x86-64
mv wrapper_*_src/lib/libwrapper.so boot/libwrapper-%{_target_os}-x86-64.so
%else
%ifarch %{aarch64}
mv wrapper_*_src/bin/wrapper boot/wrapper-%{_target_os}-arm-64
mv wrapper_*_src/lib/libwrapper.so boot/libwrapper-%{_target_os}-arm-64.so
%endif
%endif
mv -f wrapper_*_src/lib/wrapper.jar boot/
rm -rf wrapper_*_src

# Remove useless stuff:
# - blank file
rm -f build.txt
# - DOS/Windoze bits
rm -f bin/*.bat

# Minor tweaks:
# - Use correct systemd unit path for packaged services
sed -i -e "s,/etc/systemd/system,%{_unitdir},g" bin/server.sh
# - Require the Java version we built for
sed -i -e "s,wrapper.java.version.min=.*,wrapper.java.version.min=$JAVA_VERSION," conf/wrapper.conf agent/conf/wrapper.conf
# - Don't run as root
sed -i -e "s,^#RUN_AS_USER=.*,RUN_AS_USER=onedev," bin/server.sh
# - Figure out the JRE to use
sed -i -e "/^APP_NAME/i. %{_sysconfdir}/profile.d/90java.sh" bin/server.sh

%install
cd ..
mkdir -p %{buildroot}/srv
cp -a %{name}-%{version} %{buildroot}/srv/onedev

# Systemd integration
mkdir -p %{buildroot}%{_unitdir}
cat >%{buildroot}%{_unitdir}/onedev.service <<EOF
[Unit]
Description=OneDev git server platform
After=syslog.target network-online.target

[Service]
Type=forking
ExecStart=/srv/onedev/bin/server.sh start sysd
ExecStop=/srv/onedev/bin/server.sh stop sysd
User=onedev

[Install]
WantedBy=multi-user.target
EOF

# User
mkdir -p %{buildroot}%{_sysusersdir}
cp %{S:10} %{buildroot}%{_sysusersdir}/onedev.conf

# Nginx integration to the largest extent we can get
# (just "include onedev.conf;" from a vhost)
mkdir -p %{buildroot}%{_sysconfdir}/nginx
cat >%{buildroot}%{_sysconfdir}/nginx/onedev.conf <<'EOF'
client_max_body_size 10G;
location /wicket/websocket {
	proxy_pass http://localhost:6610/wicket/websocket;
	proxy_http_version 1.1;
	proxy_set_header Upgrade $http_upgrade;
	proxy_set_header Connection "upgrade";
}
location /~server {
	proxy_pass http://localhost:6610/~server;
	proxy_http_version 1.1;
	proxy_set_header Upgrade $http_upgrade;
	proxy_set_header Connection "upgrade";
}
location / {
	proxy_pass http://localhost:6610/;
}
EOF
cat >%{buildroot}%{_sysconfdir}/nginx/onedev.template <<'EOF'
# Copy this to %{_sysconfdir}/nginx/sites-available/yourhostname.yourdomain.conf and edit
# names...
server {
	listen 80;
	listen [::]:80;
	server_name yourhostname.yourdomain.ch;
	access_log /srv/onedev/logs/access_log;
	error_log /srv/onedev/logs/error_log;
	include onedev.conf;
}
# Certbot takes care of adding HTTPS versions of the site when you create
# the certificates. Use:
#	certbot --nginx -d yourhostname.yourdomain.ch,yourotherhostname.yourdomain.ch,...
EOF

# ghost log file
touch %{buildroot}/srv/onedev/logs/console.log

%pre
%sysusers_create_package onedev %{S:10}

%files
%dir %attr(-,onedev,onedev) /srv/onedev
/srv/onedev/3rdparty-licenses
/srv/onedev/agent
/srv/onedev/boot
# FIXME permissions here are too open, there's no reason
# why onedev should be able to write to its own bin directory
# (the reason why it does need to do that is that it writes
# its pid file in its bin directory instead of somewhere in
# /run) (this may be fixable by setting -Dwrapper.pidfile
# and/or -Dwrapper.java.pidfile when building tanukiwrapper)
%attr(-,onedev,onedev) /srv/onedev/bin
%attr(-,onedev,onedev) %dir /srv/onedev/conf
%config(noreplace) %attr(-,onedev,onedev) /srv/onedev/conf/hibernate.properties
%config %attr(-,onedev,onedev) /srv/onedev/conf/logback.xml
%config(noreplace) %attr(-,onedev,onedev) /srv/onedev/conf/server.properties
%config %attr(-,onedev,onedev) /srv/onedev/conf/wrapper.conf
%config %attr(-,onedev,onedev) /srv/onedev/conf/wrapper-license.conf
/srv/onedev/incompatibilities
/srv/onedev/lib
%dir %attr(-,onedev,onedev) /srv/onedev/logs
%ghost %attr(-,onedev,onedev) /srv/onedev/logs/console.log
%attr(-,onedev,onedev) /srv/onedev/site
%license /srv/onedev/license.txt
/srv/onedev/readme.txt
/srv/onedev/release.properties
%{_sysusersdir}/onedev.conf
%{_unitdir}/onedev.service
%{_sysconfdir}/nginx/*
