#!/bin/zsh
README=README.md
jupyter nbconvert --execute .readme/README.ipynb --to markdown --output ../$README
sed 1,6d $README | \
    sed -E 's/dump[(](.*)[)]/\1/g' | \
    sed 's/    |/|/g' | \
    tee | tee $README
