package com.solanaquant.persistence;

import com.solanaquant.domain.BacktestTradeEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface BacktestTradeRepository extends JpaRepository<BacktestTradeEntity, Long> {
    List<BacktestTradeEntity> findByRunIdOrderByEntryTimeAsc(UUID runId);
}
