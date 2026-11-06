#!/usr/bin/env bash
# Convert one PDF, or every PDF in a folder, to pdftext XML.
#
#   scripts/convert.sh input.pdf [out-dir] [pdftext options...]
#   scripts/convert.sh pdfs/     [out-dir] [pdftext options...]
#
# One PDF goes to <out-dir> (default: out/<name>/). A folder's PDFs each go to
# <out-dir>/<name>/ (default out-dir: out/). Options after out-dir are passed to
# pdftext, e.g. --page-timeout 10. The exit code is the worst pdftext exit code seen.
set -euo pipefail

if [[ $# -lt 1 || $1 == -h || $1 == --help ]]; then
    sed -n '2,9s/^# \{0,1\}//p' "$0"
    exit 2
fi

input=$1
shift
out=""
if [[ $# -gt 0 && $1 != -* ]]; then
    out=$1
    shift
fi

project=$(cd "$(dirname "$0")/.." && pwd)
pdftext=(uv run --quiet --project "$project" pdftext)

worst=0
convert_one() {
    local pdf=$1 dest=$2 code=0
    shift 2
    "${pdftext[@]}" "$pdf" -o "$dest" "$@" || code=$?
    case $code in
        0) echo "ok          $pdf -> $dest" ;;
        3) echo "page errors $pdf -> $dest (see status=\"error\" pages)" ;;
        2)
            echo "refused     $pdf"
            rmdir "$dest" 2>/dev/null || true # leave no empty folder behind
            ;;
        *) echo "failed      $pdf (exit $code)" ;;
    esac
    if ((code > worst)); then worst=$code; fi
}

if [[ -d $input ]]; then
    out=${out:-out}
    shopt -s nullglob nocaseglob
    pdfs=("$input"/*.pdf)
    if [[ ${#pdfs[@]} -eq 0 ]]; then
        echo "no .pdf files in $input" >&2
        exit 2
    fi
    for pdf in "${pdfs[@]}"; do
        name=$(basename "$pdf")
        convert_one "$pdf" "$out/${name%.*}" "$@"
    done
else
    name=$(basename "$input")
    convert_one "$input" "${out:-out/${name%.*}}" "$@"
fi
exit "$worst"
