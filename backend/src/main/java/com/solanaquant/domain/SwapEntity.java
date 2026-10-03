package com.solanaquant.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "swaps")
public class SwapEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tx_signature", nullable = false, unique = true)
    private String txSignature;

    @Column(name = "token_id", nullable = false)
    private Long tokenId;

    @Column(name = "wallet_id")
    private Long walletId;

    @Column(name = "wallet_address", nullable = false)
    private String walletAddress;

    @Column(nullable = false)
    private String side;

    @Column(name = "amount_token")
    private BigDecimal amountToken;

    @Column(name = "amount_usd")
    private BigDecimal amountUsd;

    @Column(name = "price_usd")
    private BigDecimal priceUsd;

    private String dex;

    @Column(name = "block_time", nullable = false)
    private Instant blockTime;

    public Long getId() {
        return id;
    }

    public Long getTokenId() {
        return tokenId;
    }

    public void setTokenId(Long tokenId) {
        this.tokenId = tokenId;
    }

    public Long getWalletId() {
        return walletId;
    }

    public void setWalletId(Long walletId) {
        this.walletId = walletId;
    }

    public String getWalletAddress() {
        return walletAddress;
    }

    public void setWalletAddress(String walletAddress) {
        this.walletAddress = walletAddress;
    }

    public String getSide() {
        return side;
    }

    public void setSide(String side) {
        this.side = side;
    }

    public String getTxSignature() {
        return txSignature;
    }

    public void setTxSignature(String txSignature) {
        this.txSignature = txSignature;
    }

    public BigDecimal getPriceUsd() {
        return priceUsd;
    }

    public void setPriceUsd(BigDecimal priceUsd) {
        this.priceUsd = priceUsd;
    }

    public Instant getBlockTime() {
        return blockTime;
    }

    public void setBlockTime(Instant blockTime) {
        this.blockTime = blockTime;
    }
}
