#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

pyuic5 annotation_window.ui -o Ui_annotation_window.py
pyinstaller --noconfirm annotation.spec
