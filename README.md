docker run -p 9090:9090 --network=host --rm -v `pwd`/prometheus.yml:/etc/prometheus/prometheus.yml prom/prometheus
docker run --rm -p 3000:3000 -v /var/lib/grafana:/var/lib/grafana grafana/grafana
