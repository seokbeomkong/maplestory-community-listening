#!/usr/bin/env bash
set -euo pipefail

readonly DEPLOY_ROOT="/opt/maple-inven-monitor"
readonly EXPORT_ROOT="$DEPLOY_ROOT/exports"
readonly RELEASE_ROOT="$EXPORT_ROOT/releases"
readonly LEASE_ROOT="$EXPORT_ROOT/inflight"
readonly RELEASE_KEEP_COUNT=3
readonly RELEASE_NAME_PATTERN='^[0-9]{8}-[0-9]{6}-[A-Za-z0-9]{8}$'
readonly CSV_FILES=(
  "latest_post_metrics.csv"
  "cumulative_top50.csv"
  "collection_runs.csv"
  "security_quarantine.csv"
)
readonly COMPOSE=(
  docker compose
  --project-directory "$DEPLOY_ROOT"
  --env-file "$DEPLOY_ROOT/.env.production"
  -f "$DEPLOY_ROOT/compose.prod.yaml"
)

staging_dir=""
container_temp_dir=""
latest_work_dir=""
latest_temp=""

remove_container_temp() {
  if [[ -z "$container_temp_dir" ]]; then
    return 0
  fi
  if [[ ! "$container_temp_dir" =~ ^/tmp/maple-inven-export-[0-9]{8}-[0-9]{6}-[A-Za-z0-9]{8}$ ]]; then
    return 1
  fi
  "${COMPOSE[@]}" exec -T postgres rm -rf -- "$container_temp_dir" >/dev/null
  container_temp_dir=""
}

cleanup() {
  if [[ -n "$staging_dir" && -d "$staging_dir" ]]; then
    rm -rf -- "$staging_dir"
  fi
  if [[ -n "$latest_work_dir" && -d "$latest_work_dir" ]]; then
    rm -rf -- "$latest_work_dir"
  fi
  remove_container_temp || true
}
trap cleanup EXIT

ensure_export_roots() {
  mkdir -p -- "$EXPORT_ROOT" "$RELEASE_ROOT" "$LEASE_ROOT"
}

acquire_export_lock() {
  exec 9>"$EXPORT_ROOT/.export.lock"
  flock -x 9
}

update_latest_download() {
  local target="$1"
  local suffix="$2"

  latest_work_dir="$(mktemp -d "$EXPORT_ROOT/.latest-download-${suffix}-XXXXXXXX")"
  latest_temp="$latest_work_dir/latest-download"
  ln -s -- "$target" "$latest_temp"
  mv -Tf -- "$latest_temp" "$EXPORT_ROOT/latest-download"
  latest_temp=""
  rmdir -- "$latest_work_dir"
  latest_work_dir=""
}

export_snapshot() {
  ensure_export_roots

  local timestamp
  local random_suffix
  local release_name
  local release_dir
  local lease_path
  local csv_file

  timestamp="$(date -u +'%Y%m%d-%H%M%S')"
  staging_dir="$(mktemp -d "$EXPORT_ROOT/.staging-${timestamp}-XXXXXXXX")"
  random_suffix="${staging_dir##*-}"
  release_name="${timestamp}-${random_suffix}"
  release_dir="$RELEASE_ROOT/$release_name"
  container_temp_dir="/tmp/maple-inven-export-$release_name"

  "${COMPOSE[@]}" exec -T postgres \
    sh -c 'umask 077; mkdir -- "$1"' sh "$container_temp_dir" >/dev/null

  "${COMPOSE[@]}" exec -T postgres \
    sh -c 'exec psql --quiet --no-psqlrc --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
    >/dev/null <<SQL
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
\o $container_temp_dir/latest_post_metrics.csv
COPY (
  -- Every stored board is in scope; the lateral query selects the latest row
  -- independently for each composite (board_id, post_id) key.
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
\o $container_temp_dir/cumulative_top50.csv
COPY (
  -- Rankings span every analysis unit and board; there is no source predicate.
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
\o $container_temp_dir/collection_runs.csv
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
\o $container_temp_dir/security_quarantine.csv
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
\o
COMMIT;
SQL

  for csv_file in "${CSV_FILES[@]}"; do
    "${COMPOSE[@]}" cp "postgres:$container_temp_dir/$csv_file" "$staging_dir/$csv_file"
  done
  remove_container_temp

  (
    cd "$staging_dir"
    sha256sum "${CSV_FILES[@]}" >SHA256SUMS.txt
  )

  acquire_export_lock
  if [[ -e "$release_dir" || -L "$release_dir" ]]; then
    printf 'release destination already exists\n' >&2
    exit 1
  fi
  mv -T -- "$staging_dir" "$release_dir"
  staging_dir=""

  lease_path="$LEASE_ROOT/$release_name"
  (set -o noclobber; : >"$lease_path")
  update_latest_download "$release_dir" "$random_suffix"

  printf '%s\n' "$release_dir"
}

cleanup_stale_leases() {
  local lease_path
  local lease_name

  while IFS= read -r lease_path; do
    lease_name="${lease_path##*/}"
    if [[ "$lease_name" =~ $RELEASE_NAME_PATTERN ]]; then
      rm -f -- "$lease_path"
    fi
  done < <(find "$LEASE_ROOT" -mindepth 1 -maxdepth 1 -type f -mmin +1440 -print)
}

prune_releases() {
  local current_path="$1"
  local current_name="${current_path##*/}"
  local latest_target
  local latest_name
  local candidate_name
  local candidate_path
  local retained=0
  local -a release_names=()

  if [[ ! "$current_name" =~ $RELEASE_NAME_PATTERN ]] || \
    [[ "$current_path" != "$RELEASE_ROOT/$current_name" ]]; then
    printf 'invalid release path for prune\n' >&2
    return 2
  fi

  ensure_export_roots
  acquire_export_lock
  if [[ ! -d "$current_path" || -L "$current_path" ]]; then
    printf 'release path is not a completed release\n' >&2
    return 2
  fi

  cleanup_stale_leases

  while IFS= read -r candidate_name; do
    if [[ "$candidate_name" =~ $RELEASE_NAME_PATTERN ]]; then
      release_names+=("$candidate_name")
    fi
  done < <(find "$RELEASE_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r)

  if ((${#release_names[@]} == 0)); then
    printf 'no completed releases available\n' >&2
    return 1
  fi

  latest_target="$(readlink "$EXPORT_ROOT/latest-download" 2>/dev/null || true)"
  latest_name="${latest_target##*/}"
  if [[ ! "$latest_name" =~ $RELEASE_NAME_PATTERN ]] || \
    [[ "$latest_target" != "$RELEASE_ROOT/$latest_name" ]] || \
    [[ ! -d "$latest_target" ]] || [[ -L "$latest_target" ]]; then
    latest_name="${release_names[0]}"
  fi
  update_latest_download "$RELEASE_ROOT/$latest_name" "prune-${current_name##*-}"

  for candidate_name in "${release_names[@]}"; do
    candidate_path="$RELEASE_ROOT/$candidate_name"
    if [[ -f "$LEASE_ROOT/$candidate_name" ]] || \
      [[ "$candidate_name" == "$current_name" ]] || \
      [[ "$candidate_name" == "$latest_name" ]]; then
      ((retained += 1))
      continue
    fi
    if ((retained < RELEASE_KEEP_COUNT)); then
      ((retained += 1))
      continue
    fi
    if [[ -d "$candidate_path" && ! -L "$candidate_path" ]]; then
      rm -rf -- "$candidate_path"
    fi
  done

  rm -f -- "$LEASE_ROOT/$current_name"
}

case "$#" in
  0)
    export_snapshot
    ;;
  2)
    if [[ "$1" != "--prune" ]]; then
      printf 'unsupported export helper option\n' >&2
      exit 2
    fi
    prune_releases "$2"
    ;;
  *)
    printf 'usage: export-production-csv.sh [--prune ABSOLUTE_RELEASE_PATH]\n' >&2
    exit 2
    ;;
esac
