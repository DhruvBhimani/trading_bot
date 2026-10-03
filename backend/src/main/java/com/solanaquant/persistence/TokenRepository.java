package com.solanaquant.persistence;

import com.solanaquant.domain.TokenEntity;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface TokenRepository extends JpaRepository<TokenEntity, Long> {
    Optional<TokenEntity> findByMintAddress(String mintAddress);

    long count();
}
