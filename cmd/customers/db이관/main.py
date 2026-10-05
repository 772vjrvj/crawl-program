"""PostgreSQL address_cache -> MariaDB GEO_ADDRESS_CACHE. 기본은 검증만 수행."""
import argparse
import json
import math
import sys
import time
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

SELECT_ROWS = """
              SELECT id, ST_Y(geom) AS lat, ST_X(geom) AS lng,
                     address_data, road_address_data, updated_at
              FROM public.address_cache ORDER BY id \
              """
INSERT_ROW = """
             INSERT INTO GEO_ADDRESS_CACHE
                 (ID, COORD_KEY, LAT, LNG, ADDRESS_DATA, ROAD_ADDRESS_DATA, UPDATED_AT)
             VALUES (%s, %s, %s, %s, %s, %s, %s) \
             """


def log(message):
    print(time.strftime("[%H:%M:%S]"), message, flush=True)


def coord_key(lat, lng):
    # Java BigDecimal.valueOf(double).setScale(6, HALF_EVEN)와 같은 기준.
    def rounded(value):
        return format(Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN), "f")
    return rounded(lat) + "," + rounded(lng)


def json_object(value):
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        value = {}
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def convert_row(row):
    row_id, lat, lng, address, road, updated_at = row
    if lat is None or lng is None:
        raise ValueError(f"ID={row_id}: 좌표 없음. 이전을 중단합니다.")
    lat, lng = float(lat), float(lng)
    if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90
            and -180 <= lng <= 180 and lat != 0 and lng != 0):
        raise ValueError(f"ID={row_id}: 유효하지 않은 좌표. 이전을 중단합니다.")
    return (int(row_id), coord_key(lat, lng), lat, lng,
            json_object(address), json_object(road), updated_at)


def load_config(path):
    with Path(path).open(encoding="utf-8-sig") as f:
        cfg = json.load(f)
    for name in ("postgresql", "mariadb"):
        db = cfg.get(name)
        if not isinstance(db, dict):
            raise ValueError(f"config.json에 {name} 설정이 필요합니다.")
        for key in ("host", "database", "user", "password"):
            if key not in db or not isinstance(db[key], str):
                raise ValueError(f"{name}.{key}는 문자열로 입력하세요.")
            if key != "password" and not db[key].strip():
                raise ValueError(f"{name}.{key}가 비어 있습니다.")
    cfg["batch_size"] = int(cfg.get("batch_size", 1000))
    if not 1 <= cfg["batch_size"] <= 5000:
        raise ValueError("batch_size는 1~5000으로 설정하세요.")
    return cfg


def copy_data(pg, maria, batch_size, apply):
    """연결은 호출자가 소유. MariaDB 쓰기 실패/중단 시 호출자가 rollback."""
    with pg.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM public.address_cache")
        total = cur.fetchone()[0]
    with maria.cursor() as cur:
        # 컬럼도 실제로 있는지 확인. 기존 데이터를 덮어쓰지 않는다.
        cur.execute("SELECT ID, COORD_KEY, LAT, LNG, ADDRESS_DATA, ROAD_ADDRESS_DATA, UPDATED_AT "
                    "FROM GEO_ADDRESS_CACHE LIMIT 0")
        cur.execute("SELECT COUNT(*) FROM GEO_ADDRESS_CACHE")
        target_count = cur.fetchone()[0]
        cur.execute("SELECT ENGINE FROM information_schema.TABLES "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s", ("GEO_ADDRESS_CACHE",))
        engine = cur.fetchone()
    if not engine or str(engine[0]).upper() != "INNODB":
        raise ValueError("대상 테이블은 롤백 가능한 InnoDB여야 합니다.")
    if target_count != 0:
        raise ValueError(f"대상 테이블에 {target_count:,}건이 있습니다. 덮어쓰지 않고 중단합니다.")
    log(f"원본 {total:,}건 / 대상 0건 / {'실제 이전' if apply else '검증만'}")
    done = 0
    # 서버측 커서로 읽으므로 원본 전체를 PC 메모리에 올리지 않는다.
    with pg.cursor(name="address_migration_stream") as source, maria.cursor() as target:
        source.itersize = batch_size
        source.execute(SELECT_ROWS)
        while True:
            rows = source.fetchmany(batch_size)
            if not rows:
                break
            converted = [convert_row(row) for row in rows]
            if apply:
                target.executemany(INSERT_ROW, converted)
            done += len(converted)
            log(f"{'이전' if apply else '검증'} 진행 {done:,}/{total:,}건"
                + (" (아직 커밋 전)" if apply else ""))
    if done != total:
        raise ValueError(f"건수 불일치: 원본 {total:,}, 처리 {done:,}")
    if apply:
        with maria.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM GEO_ADDRESS_CACHE")
            actual = cur.fetchone()[0]
        if actual != done:
            raise ValueError(f"대상 건수 불일치: 처리 {done:,}, 저장 {actual:,}")
        log("모든 데이터 처리/건수 확인 완료. COMMIT 중...")
        maria.commit()
        log(f"COMMITTED: {done:,}건 이전 완료 / PostgreSQL 원본 변경 없음")
    else:
        log(f"DRY RUN 완료: {done:,}건 검증 / DB 변경 없음. 실제 이전은 --apply")
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--apply", action="store_true", help="실제 INSERT 후 전체 성공 시 커밋")
    args = parser.parse_args()
    pg = maria = None
    started = time.monotonic()
    try:
        try:
            import psycopg2
            import pymysql
        except ImportError:
            raise RuntimeError("드라이버가 필요합니다: python -m pip install -r requirements.txt") from None
        cfg = load_config(args.config)
        p, m = cfg["postgresql"], cfg["mariadb"]
        log("PostgreSQL 연결 시작...")
        pg = psycopg2.connect(host=p["host"], port=int(p.get("port", 5432)),
                              dbname=p["database"], user=p["user"], password=p["password"],
                              connect_timeout=10)
        # 같은 스냅샷에서 count/데이터를 읽고 원본 변경을 금지.
        pg.set_session(isolation_level="REPEATABLE READ", readonly=True, autocommit=False)
        log("PostgreSQL 연결 완료 / MariaDB 연결 시작...")
        maria = pymysql.connect(host=m["host"], port=int(m.get("port", 3306)),
                                database=m["database"], user=m["user"], password=m["password"],
                                charset="utf8mb4", autocommit=False, connect_timeout=10,
                                read_timeout=600, write_timeout=600)
        log("MariaDB 연결 완료")
        # 메타데이터가 아닌 입력 원문/비밀번호는 로그에 출력하지 않는다.
        copy_data(pg, maria, cfg["batch_size"], args.apply)
        return 0
    except BaseException as exc:
        # COMMIT 통신 실패는 결과가 불확실할 수 있으므로 성공을 주장하지 않는다.
        if maria is not None:
            try:
                maria.rollback()
                log("ROLLBACK 실행. COMMITTED가 나오지 않았다면 대상 건수를 확인하세요.")
            except Exception:
                log("연결 장애로 ROLLBACK 확인 불가. 대상 테이블의 건수를 확인하세요.")
        if isinstance(exc, KeyboardInterrupt):
            log("사용자 중단")
        else:
            log(f"실패: {exc}")
        return 1
    finally:
        if pg is not None:
            try:
                pg.rollback()
                pg.close()
            except Exception:
                pass
        if maria is not None:
            try:
                maria.close()
            except Exception:
                pass
        log(f"총 소요 {time.monotonic()-started:.1f}초")


if __name__ == "__main__":
    sys.exit(main())
