import logging
import signal
import sys
import time

from sllurp.llrp import LLRPReaderConfig, LLRPReaderClient, LLRP_DEFAULT_PORT

READER_IP = "169.254.1.1"
READER_PORT = LLRP_DEFAULT_PORT

# Логирование для отладки
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("sllurp").setLevel(logging.INFO)


def tag_report_cb(reader, tag_reports):
    for tag in tag_reports:
        epc = tag.get("EPC") or tag.get("EPC-96") or tag.get("EPCData") or b""
        if isinstance(epc, bytes):
            epc = epc.hex()
        else:
            epc = str(epc)

        rssi = tag.get("PeakRSSI", "N/A")
        ant = tag.get("AntennaID", "N/A")

        ts = time.strftime("%H:%M:%S")
        epc_short = f"...{epc[-4:]}" if len(epc) >= 4 else epc
        print(f"[{ts}] АНТ: {ant} | RSSI: {rssi} dBm | EPC: {epc_short}")


def main():
    config = LLRPReaderConfig()

    # антенны и мощность (87 = макс. индекс для R420)
    config.antennas = [1, 2, 3, 4]
    config.tx_power = {1: 87, 2: 87, 3: 87, 4: 87}

    # режим и сессия
    config.mode_identifier = 1004
    config.session = 2
    config.tag_population = 1
    config.report_every_n_tags = 1

    # включить RSSI и Antenna ID в отчёты
    config.tag_content_selector["EnableAntennaID"] = True
    config.tag_content_selector["EnablePeakRSSI"] = True

    client = LLRPReaderClient(READER_IP, READER_PORT, config=config)
    client.add_tag_report_callback(tag_report_cb)

    def shutdown(signum=None, frame=None):
        print("\nОстановка...")
        try:
            client.disconnect()
        except Exception:
            pass
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"--- Подключение к {READER_IP}:{READER_PORT} ---")
    print("Impinj R420 | Режим: 1004 | Мощность: макс | Антенны: 1-4")
    print("Подносите метки к антеннам. Ctrl+C для выхода.\n")

    try:
        client.connect()
        print("Подключено. Ожидание меток...\n")
        client.join(None)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Ошибка: {e}")
        logging.exception("Детали:")
        sys.exit(1)
    finally:
        shutdown()


if __name__ == "__main__":
    main()
