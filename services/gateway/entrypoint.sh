#!/bin/sh
set -e
# ACA environment DNS server (from the container's resolv.conf) unless overridden.
export DNS_RESOLVER="${DNS_RESOLVER:-$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf)}"
export ENV_SUFFIX="${ENV_SUFFIX:-dev-sdc}"
envsubst '${DNS_RESOLVER} ${ENV_SUFFIX}' \
  < /etc/nginx/nginx.conf.template \
  > /etc/nginx/nginx.conf
exec nginx -g 'daemon off;'
