#!/usr/bin/env bash
# Convert one PDF, or every PDF in a folder, to pdftext XML.
#
#   scripts/convert.sh input.pdf [out-dir] [pdftext options...]
#   scripts/convert.sh pdfs/     [out-dir] [pdftext options...]
#
# One PDF goes to <out-dir> (default: out/<name>/). A folder's PDFs each go to
# <out-dir>/<name>/ (default out-dir: out/); a PDF whose folder name matches an
# earlier one's, ignoring case (x.pdf and x.PDF), is skipped as refused. Options after
# out-dir are passed to pdftext, e.g. --page-timeout 10; -o and --output are not accepted.
# The exit code is the most severe pdftext exit code seen: 1 (the output can't be
# written, or an internal error), then 2 (refused or run stopped), then 3 (page
# errors), then 0.
set -euo pipefail

usage() {
    sed -n '/^set /q; 2,$s/^# \{0,1\}//p' "$0"
}

# Print a file name with control characters (C0, DEL, C1) replaced, so that a crafted name
# can't send terminal escape sequences or fake a status line. Works on bytes, because a C1
# character is the two UTF-8 bytes C2 80 to C2 9F.
printable() {
    local LC_ALL=C name=$1
    name=${name//[[:cntrl:]]/?}
    printf '%s\n' "${name//$'\xc2'[$'\x80'-$'\x9f']/?}"
}

if [[ $# -lt 1 ]]; then
    usage >&2
    exit 2
fi
if [[ $1 == -h || $1 == --help ]]; then
    usage
    exit 0
fi

input=$1
shift
out=""
if [[ $# -gt 0 && $1 != -* ]]; then
    out=$1
    shift
fi

for option in "$@"; do
    if [[ $option == -o* || $option == --o* ]]; then # --o* also catches abbreviations
        echo "the script sets the output folder: use [out-dir], not $(printable "$option")" >&2
        exit 2
    fi
done

project=$(cd "$(dirname "$0")/.." && pwd)
pdftext=(uv run --quiet --project "$project" pdftext)

# Higher is worse: 1 (write failure or internal error), 2 (refused), 3 (page errors), 0.
severity() {
    case $1 in
        1) echo 3 ;;
        2) echo 2 ;;
        3) echo 1 ;;
        *) echo 0 ;;
    esac
}

worst=0
record_exit_code() {
    if (($(severity "$1") > $(severity "$worst"))); then worst=$1; fi
}

convert_one() {
    local pdf=$1 dest=$2 code=0 shown_pdf shown_dest
    shift 2
    shown_pdf=$(printable "$pdf")
    shown_dest=$(printable "$dest")
    "${pdftext[@]}" "$pdf" -o "$dest" "$@" || code=$?
    case $code in
        0) echo "ok          $shown_pdf -> $shown_dest" ;;
        3) echo "page errors $shown_pdf -> $shown_dest (see status=\"error\" pages)" ;;
        2)
            echo "refused     $shown_pdf"
            rmdir "$dest" 2>/dev/null || true # leave no empty folder behind
            ;;
        *)
            echo "failed      $shown_pdf (exit $code)"
            code=1
            ;;
    esac
    record_exit_code "$code"
}

if [[ -d $input ]]; then
    out=${out:-out}
    shopt -s nullglob nocaseglob
    pdfs=("$input"/*.pdf)
    if [[ ${#pdfs[@]} -eq 0 ]]; then
        echo "no .pdf files in $(printable "$input")" >&2
        exit 2
    fi
    used_folders=() # lower case, so that x.pdf and x.PDF are found to share a folder
    for pdf in "${pdfs[@]}"; do
        name=$(basename "$pdf")
        folder=$(printf '%s' "${name%.*}" | tr '[:upper:]' '[:lower:]')
        shared=false
        for used in ${used_folders[@]+"${used_folders[@]}"}; do
            if [[ $used == "$folder" ]]; then shared=true; fi
        done
        if $shared; then
            echo "refused     $(printable "$pdf") (same output folder as an earlier PDF)"
            record_exit_code 2
            continue
        fi
        used_folders+=("$folder")
        convert_one "$pdf" "$out/${name%.*}" "$@"
    done
else
    name=$(basename "$input")
    convert_one "$input" "${out:-out/${name%.*}}" "$@"
fi
exit "$worst"
