FROM dpage/pgadmin4:9.18
COPY --chown=5050:0 bootstrap.py /bootstrap.py
ENTRYPOINT ["/venv/bin/python3", "/bootstrap.py"]
