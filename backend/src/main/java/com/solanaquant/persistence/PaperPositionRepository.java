package com.solanaquant.persistence;

import com.solanaquant.domain.PaperPositionEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface PaperPositionRepository extends JpaRepository<PaperPositionEntity, Long> {
    List<PaperPositionEntity> findByAccountIdAndStatus(Long accountId, String status);
}
