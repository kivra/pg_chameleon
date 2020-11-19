FROM python:3.9.0-alpine3.12

RUN \
 apk --update add --no-cache postgresql-libs && \
 apk add --no-cache --virtual .build-deps gcc musl-dev postgresql-dev && \
 apk --update add --no-cache postgresql-client git

COPY . /build
WORKDIR /build

RUN python setup.py install

RUN apk --purge del .build-deps

ENTRYPOINT ["chameleon", "--allow-root"]
