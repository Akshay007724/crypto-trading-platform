from hft.connectors.kraken import parse_trade_message
from hft.types import Trade


def test_parses_single_trade_update_into_normalized_trades():
    # Arrange: real message shape captured from wss://ws.kraken.com/v2 trade channel
    raw = (
        '{"channel":"trade","type":"update","data":[{"symbol":"BTC/USD",'
        '"side":"buy","price":77120.0,"qty":0.00048389,"ord_type":"limit",'
        '"trade_id":105702534,"timestamp":"2026-08-22T17:30:53.355059Z"}]}'
    )

    # Act
    trades = parse_trade_message(raw)

    # Assert
    assert trades == [
        Trade(exchange="kraken", symbol="BTC/USD", price=77120.0, size=0.00048389, side="buy", ts=1787419853)
    ]


def test_parses_multiple_trades_in_one_update():
    # Arrange: Kraken batches multiple fills into one "data" array
    raw = (
        '{"channel":"trade","type":"update","data":['
        '{"symbol":"ETH/USD","side":"sell","price":3200.5,"qty":0.1,"ord_type":"market",'
        '"trade_id":1,"timestamp":"2026-08-22T17:30:53.000000Z"},'
        '{"symbol":"ETH/USD","side":"buy","price":3201.0,"qty":0.2,"ord_type":"limit",'
        '"trade_id":2,"timestamp":"2026-08-22T17:30:54.000000Z"}]}'
    )

    # Act
    trades = parse_trade_message(raw)

    # Assert
    assert [t.side for t in trades] == ["sell", "buy"]
    assert [t.price for t in trades] == [3200.5, 3201.0]


def test_non_trade_messages_produce_no_trades():
    # Arrange: heartbeats and subscription acks are not trade updates
    heartbeat = '{"channel":"heartbeat"}'
    ack = '{"method":"subscribe","result":{"channel":"trade"},"success":true}'

    # Act / Assert
    assert parse_trade_message(heartbeat) == []
    assert parse_trade_message(ack) == []
