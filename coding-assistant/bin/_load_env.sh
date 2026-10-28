# Sourced by the wrappers. Read only known settings; never source/execute .env.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

# read_kv FILE KEY... : collect literal values as FILE_KEY variables.
read_kv() {
  local file="$1"; shift
  local key value wanted
  while IFS='=' read -r key value || [ -n "$key" ]; do
    key="$(trim "$key")"
    key="${key#export }"
    key="$(trim "$key")"
    for wanted in "$@"; do
      if [ "$key" = "$wanted" ]; then
        value="$(trim "$value")"
        case "$value" in
          \"*\") value="${value#\"}"; value="${value%\"}" ;;
          \'*\') value="${value#\'}"; value="${value%\'}" ;;
          *) value="$(trim "${value%%[[:space:]]\#*}")" ;;
        esac
        export "FILE_$key=$value"
      fi
    done
  done < "$file"
}

load_config() {
  local profile="$1" key file_key
  local settings=(LLM_API_KEY AZURE_FOUNDRY_API_KEY)
  case "$profile" in
    luna) settings+=(LLM_BASE_URL LUNA_OPENAI_BASE_URL LUNA_DEPLOYMENT) ;;
    haiku) settings+=(HAIKU_ANTHROPIC_BASE_URL HAIKU_DEPLOYMENT) ;;
  esac

  if [ -f "$REPO_ROOT/.env" ]; then
    [ -r "$REPO_ROOT/.env" ] || { echo "error: cannot read the root .env file" >&2; exit 1; }
    read_kv "$REPO_ROOT/.env" "${settings[@]}"
  fi
  # An already-exported, nonempty setting wins over the root .env file.
  for key in "${settings[@]}"; do
    file_key="FILE_$key"
    if [ -z "${!key:-}" ]; then
      export "$key=${!file_key:-}"
    fi
    unset "$file_key"
  done

  export AZURE_FOUNDRY_API_KEY="${AZURE_FOUNDRY_API_KEY:-${LLM_API_KEY:-}}"
  if [ "$profile" = luna ]; then
    export LUNA_OPENAI_BASE_URL="${LUNA_OPENAI_BASE_URL:-${LLM_BASE_URL:-}}"
    settings=(LUNA_OPENAI_BASE_URL LUNA_DEPLOYMENT)
  else
    settings=(HAIKU_ANTHROPIC_BASE_URL HAIKU_DEPLOYMENT)
  fi

  local missing=""
  for key in "${settings[@]}"; do
    [ -n "${!key:-}" ] || missing="$missing $key"
  done
  [ -n "$AZURE_FOUNDRY_API_KEY" ] || missing="$missing LLM_API_KEY (or AZURE_FOUNDRY_API_KEY)"
  if [ -n "$missing" ]; then
    echo "error: set in the root .env:$missing" >&2
    echo "       Copy .example.env to .env if needed; see coding-assistant/README.md." >&2
    exit 1
  fi
}
