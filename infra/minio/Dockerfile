# Local development/test only: upstream CE is source-only and archived.
FROM golang:1.27.1-bookworm AS build
ENV CGO_ENABLED=0 GOTOOLCHAIN=local
WORKDIR /src
RUN git clone https://github.com/minio/minio.git . \
    && git checkout --detach 7aac2a2c5b7c882e68c1ce017d8256be2feea27f \
    && go build -trimpath -o /out/minio .

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 minio \
    && useradd --system --uid 1000 --gid minio minio \
    && mkdir /data && chown minio:minio /data
COPY --from=build /out/minio /usr/local/bin/minio
COPY --from=build /src/LICENSE /usr/share/doc/minio/LICENSE
USER minio
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
