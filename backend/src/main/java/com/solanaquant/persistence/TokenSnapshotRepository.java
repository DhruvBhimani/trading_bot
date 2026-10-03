package com.solanaquant.persistence;

import com.solanaquant.domain.TokenSnapshotEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface TokenSnapshotRepository extends JpaRepository<TokenSnapshotEntity, Long> {
    List<TokenSnapshotEntity> findByTokenIdOrderByObservedAtAsc(Long tokenId);

    List<TokenSnapshotEntity> findTop50ByOrderByObservedAtDesc();
}
