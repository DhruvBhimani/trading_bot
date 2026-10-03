package com.solanaquant.persistence;

import com.solanaquant.domain.SignalEventEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface SignalEventRepository extends JpaRepository<SignalEventEntity, Long> {
    List<SignalEventEntity> findTop100ByOrderByObservedAtDesc();
}
