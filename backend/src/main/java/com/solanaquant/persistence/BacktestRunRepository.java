package com.solanaquant.persistence;

import com.solanaquant.domain.BacktestRunEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.UUID;

public interface BacktestRunRepository extends JpaRepository<BacktestRunEntity, UUID> {
}
