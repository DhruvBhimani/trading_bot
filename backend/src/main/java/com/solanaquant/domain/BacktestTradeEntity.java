package com.solanaquant.domain;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;

@Entity
@Table(name = "backtest_trades")
public class BacktestTradeEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "run_id", nullable = false)
    private UUID runId;

    @Column(name = "token_id")
    private Long tokenId;

    @Column(name = "mint_address")
    private String mintAddress;

    @Column(name = "entry_time")
    private Instant entryTime;

    @Column(name = "exit_time")
    private Instant exitTime;

    @Column(name = "entry_price")
    private BigDecimal entryPrice;

    @Column(name = "exit_price")
    private BigDecimal exitPrice;

    @Column(name = "pnl_pct")
    private BigDecimal pnlPct;

    @Column(name = "exit_reason")
    private String exitReason;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "signal_details", nullable = false)
    private Map<String, Object> signalDetails;

    public void setRunId(UUID runId) {
        this.runId = runId;
    }

    public void setTokenId(Long tokenId) {
        this.tokenId = tokenId;
    }

    public void setMintAddress(String mintAddress) {
        this.mintAddress = mintAddress;
    }

    public void setEntryTime(Instant entryTime) {
        this.entryTime = entryTime;
    }

    public void setExitTime(Instant exitTime) {
        this.exitTime = exitTime;
    }

    public void setEntryPrice(BigDecimal entryPrice) {
        this.entryPrice = entryPrice;
    }

    public void setExitPrice(BigDecimal exitPrice) {
        this.exitPrice = exitPrice;
    }

    public void setPnlPct(BigDecimal pnlPct) {
        this.pnlPct = pnlPct;
    }

    public void setExitReason(String exitReason) {
        this.exitReason = exitReason;
    }

    public void setSignalDetails(Map<String, Object> signalDetails) {
        this.signalDetails = signalDetails;
    }

    public String getMintAddress() {
        return mintAddress;
    }

    public BigDecimal getPnlPct() {
        return pnlPct;
    }

    public String getExitReason() {
        return exitReason;
    }
}
