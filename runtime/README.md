# crawler-runtime

将本目录复制到爬虫项目，或在爬虫镜像构建时安装：

```dockerfile
COPY runtime /tmp/crawler-runtime
RUN pip install /tmp/crawler-runtime && rm -rf /tmp/crawler-runtime
```

平台的 `PYTHON_METHOD` 模式最终执行：

```bash
python -m crawler_runtime \
  --entrypoint openApi.ufl.ufl_inventory:wms_uf_eplusss_inventory \
  --args-json '[]' \
  --kwargs-json '{"site":"HK"}'
```
