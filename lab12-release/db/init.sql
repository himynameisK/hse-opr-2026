CREATE DATABASE metabase;
CREATE USER dashboard WITH PASSWORD 'dashboard-read-only';
CREATE TABLE attempts (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  release text NOT NULL,
  http_status integer NOT NULL,
  outcome text NOT NULL,
  amount_kopecks integer NOT NULL,
  latency_ms integer NOT NULL,
  synthetic_history boolean NOT NULL DEFAULT false
);
CREATE TABLE releases (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  version text NOT NULL
);
GRANT CONNECT ON DATABASE shop TO dashboard;
GRANT USAGE ON SCHEMA public TO dashboard;
GRANT SELECT ON attempts, releases TO dashboard;
-- Фоновая учебная история только для Metabase. Live-метрики Prometheus начинаются с запуска.
INSERT INTO attempts(created_at, release, http_status, outcome, amount_kopecks, latency_ms, synthetic_history)
SELECT now() - i * interval '1 second', 'v1', 200, 'paid', 150000, 80, true
FROM generate_series(1,900) AS i;
