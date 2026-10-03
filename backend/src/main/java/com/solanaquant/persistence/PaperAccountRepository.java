package com.solanaquant.persistence;

import com.solanaquant.domain.PaperAccountEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface PaperAccountRepository extends JpaRepository<PaperAccountEntity, Long> {
    Optional<PaperAccountEntity> findByName(String name);
}
