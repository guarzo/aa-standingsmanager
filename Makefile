appname = aa-standingssync
package = standingssync
myauth_path = ../myauth/manage.py

help:
	@echo "Makefile for $(appname)"
makemessages:
	cd $(package) && \
	django-admin makemessages \
		-l de \
		-l en \
		-l es \
		-l fr_FR \
		-l it_IT \
		-l ja \
		-l ko_KR \
		-l ru \
		-l uk \
		-l zh_Hans \
		--keep-pot \
		--ignore 'build/*'

tx_push:
	tx push --source

tx_pull:
	tx pull -f

compilemessages:
	cd $(package) && \
	django-admin compilemessages \
		-l de \
		-l en \
		-l es \
		-l fr_FR \
		-l it_IT \
		-l ja \
		-l ko_KR \
		-l ru \
		-l uk \
		-l zh_Hans

coverage:
	# coverage run $(myauth_path) test $(package).tests --keepdb --failfast -v 2 && coverage html && coverage report -m
	coverage run --concurrency=multiprocessing $(myauth_path) test $(package).tests --keepdb --failfast --timing --parallel && coverage combine && coverage html && coverage report -m

graph_models:
	python $(myauth_path) graph_models $(package) --arrow-shape normal -o $(appname)_models.png
