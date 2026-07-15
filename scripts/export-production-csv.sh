#!/usr/bin/env bash
set -euo pipefail

readonly DEPLOY_ROOT="/opt/maple-inven-monitor"
readonly EXPORT_ROOT="$DEPLOY_ROOT/exports"
readonly RELEASE_ROOT="$EXPORT_ROOT/releases"
readonly CSV_FILES=(
  "latest_post_metrics.csv"
  "cumulative_top50.csv"
  "collection_runs.csv"
  "security_quarantine.csv"
)

staging_dir=""
latest_work_dir=""
latest_temp=""

cleanup() {
  if [[ -n "$staging_dir" && -d "$staging_dir" ]]; then
    rm -rf -- "$staging_dir"
  fi
  if [[ -n "$latest_work_dir" && -d "$latest_work_dir" ]]; then
    rm -rf -- "$latest_work_dir"
  fi
}
trap cleanup EXIT

mkdir -p -- "$EXPORT_ROOT" "$RELEASE_ROOT"
timestamp="$(date -u +'%Y%m%d-%H%M%S')"
staging_dir="$(mktemp -d "$EXPORT_ROOT/.staging-${timestamp}-XXXXXXXX")"
random_suffix="${staging_dir##*-}"
release_dir="$RELEASE_ROOT/${timestamp}-${random_suffix}"

run_copy() {
  local output_file="$1"
  docker compose \
    --project-directory "$DEPLOY_ROOT" \
    --env-file "$DEPLOY_ROOT/.env.production" \
    -f "$DEPLOY_ROOT/compose.prod.yaml" \
    exec -T postgres \
    sh -c 'exec psql --quiet --no-psqlrc --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
    >"$staging_dir/$output_file"
}

run_copy "latest_post_metrics.csv" <<'SQL'
COPY (
  SELECT
    p.board_id,
    b.name AS board_name,
    p.post_id,
    p.analysis_unit,
    p.title,
    p.published_at,
    p.source_url,
    p.current_category,
    metrics.observed_at_slot_kst,
    metrics.observed_at_actual,
    metrics.views,
    metrics.recommendations,
    metrics.comments,
    metrics.config_version
  FROM posts AS p
  JOIN boards AS b ON b.id = p.board_id
  JOIN LATERAL (
    SELECT snapshot.*
    FROM post_metric_snapshots AS snapshot
    WHERE snapshot.board_id = p.board_id AND snapshot.post_id = p.post_id
    ORDER BY snapshot.observed_at_slot_kst DESC
    LIMIT 1
  ) AS metrics ON TRUE
  ORDER BY p.board_id, p.post_id
) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);
SQL

run_copy "cumulative_top50.csv" <<'SQL'
COPY (
  SELECT
    ranking.analysis_unit,
    ranking.metric,
    ranking.as_of_slot_kst,
    ranking.rank,
    ranking.board_id,
    ranking.post_id,
    posts.title,
    posts.source_url,
    ranking.metric_value,
    ranking.config_version
  FROM cumulative_top_posts AS ranking
  JOIN posts
    ON posts.board_id = ranking.board_id AND posts.post_id = ranking.post_id
  WHERE ranking.rank <= 50
    AND ranking.as_of_slot_kst = (
      SELECT max(candidate.as_of_slot_kst)
      FROM cumulative_top_posts AS candidate
      WHERE candidate.analysis_unit = ranking.analysis_unit
        AND candidate.metric = ranking.metric
    )
  ORDER BY ranking.analysis_unit, ranking.metric, ranking.rank
) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);
SQL

run_copy "collection_runs.csv" <<'SQL'
COPY (
  SELECT
    id,
    job_type,
    scheduled_at_slot_kst,
    status,
    config_version,
    started_at,
    finished_at,
    diagnostics
  FROM collection_runs
  ORDER BY scheduled_at_slot_kst DESC, job_type, id
) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);
SQL

run_copy "security_quarantine.csv" <<'SQL'
COPY (
  SELECT
    id,
    source_kind,
    source_ref,
    content_hash,
    findings,
    risk_score,
    quarantined_at,
    review_state,
    reviewer,
    note,
    released_at
  FROM security_quarantine
  ORDER BY quarantined_at DESC, id
) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);
SQL

(
  cd "$staging_dir"
  sha256sum "${CSV_FILES[@]}" >SHA256SUMS.txt
)

if [[ -e "$release_dir" || -L "$release_dir" ]]; then
  printf 'release destination already exists\n' >&2
  exit 1
fi
mv -T -- "$staging_dir" "$release_dir"
staging_dir=""

latest_work_dir="$(mktemp -d "$EXPORT_ROOT/.latest-download-${random_suffix}-XXXXXXXX")"
latest_temp="$latest_work_dir/latest-download"
ln -s -- "$release_dir" "$latest_temp"
mv -Tf -- "$latest_temp" "$EXPORT_ROOT/latest-download"
latest_temp=""
rmdir -- "$latest_work_dir"
latest_work_dir=""

printf '%s\n' "$release_dir"
