#!/bin/bash
exec gunicorn --timeout 120 --workers 2 --bind 0.0.0.0:$PORT app:app
