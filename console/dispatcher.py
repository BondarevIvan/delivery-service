"""Серверное автоназначение: раздаёт готовые заказы курьерам на точке.

Периодически спрашивает у координатора, кому какой заказ назначить
(`/auto/coordinate` -> order_to_courier) и применяет это в orders (`attach`).
Курьеры, которые ещё не на точке, в распределении не участвуют, поэтому заказ
уедет к ним, как только они отметятся «на точке».
"""
import asyncio
import logging

log = logging.getLogger("console.dispatcher")


async def dispatch_once(upstream) -> int:
    """Один проход автоназначения. Возвращает число назначенных заказов."""
    resp = await upstream.coordinator("POST", "/auto/coordinate")
    if resp.status_code != 200:
        return 0
    try:
        mapping = resp.json().get("order_to_courier", {})
    except ValueError:
        return 0

    assigned = 0
    for order_id, courier_id in mapping.items():
        result = await upstream.orders(
            "POST", "/order/attach",
            {"order_id": int(order_id), "deliver_id": int(courier_id)},
        )
        if 200 <= result.status_code < 300:
            assigned += 1
    return assigned


async def run_forever(upstream, interval: float) -> None:
    """Фоновой цикл автоназначения."""
    while True:
        try:
            await dispatch_once(upstream)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - фоновой цикл не должен падать
            log.warning("auto-dispatch failed: %s", exc)
        await asyncio.sleep(interval)
