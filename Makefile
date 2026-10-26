# 广州市民诉求数据采集与分析 · 常用命令
# 用法: make <target>

PY ?= python3
DATA ?= collected_all13_20260914.jsonl
CENSOR ?= "2026-09-15 06:42:00"

.PHONY: help check probe preflight crawl lda survival export clean

help:
	@echo "make check      环境自检（发 2 个真实请求）"
	@echo "make probe      探测 13 板块可采范围（约 16 分钟）"
	@echo "make preflight  零网络预检窗口命中条数"
	@echo "make crawl      启动采集（Windows 用 run_scraper_win.py）"
	@echo "make lda        全量 LDA 主题建模"
	@echo "make survival   生存分析（需指定 CENSOR 快照时刻）"
	@echo "make export     导出全字段 Excel"
	@echo "make clean      清理运行期产物"

check:
	$(PY) check_env.py

probe:
	$(PY) probe_window.py

preflight:
	$(PY) preflight_window.py

crawl:
	./start.sh

lda:
	$(PY) content_lda.py --input $(DATA) --kmin 6 --kmax 18 --kstep 2 --min-df 5 --topn 15

survival:
	$(PY) survival_cox.py --input $(DATA) --censor $(CENSOR)

export:
	$(PY) export_excel.py

clean:
	rm -rf __pycache__ tools/__pycache__ legacy/__pycache__ .pytest_cache
	rm -f scraper.pid
	@echo "已清理（数据与结果未删除）"
