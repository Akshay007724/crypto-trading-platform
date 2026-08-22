from hft.data import CsvTradeSource


def test_reads_trades_from_csv_in_ts_order(tmp_path):
    # Arrange
    csv_file = tmp_path / "trades.csv"
    csv_file.write_text(
        "exchange,symbol,price,size,side,ts\n"
        "binance,BTC-USD,50000,0.1,buy,2\n"
        "binance,BTC-USD,49990,0.2,sell,1\n"
    )

    # Act
    trades = list(CsvTradeSource(csv_file).trades())

    # Assert
    assert [t.ts for t in trades] == [1, 2]
    assert trades[0].price == 49990
    assert trades[0].side == "sell"
