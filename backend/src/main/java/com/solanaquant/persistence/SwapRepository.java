package com.solanaquant.persistence;

import com.solanaquant.domain.SwapEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;

public interface SwapRepository extends JpaRepository<SwapEntity, Long> {

    @Query("""
            select s from SwapEntity s
            where s.tokenId = :tokenId
              and s.blockTime <= :asOf
              and s.blockTime >= :since
            order by s.blockTime asc
            """)
    List<SwapEntity> findTokenSwapsBetween(
            @Param("tokenId") Long tokenId,
            @Param("since") Instant since,
            @Param("asOf") Instant asOf
    );

    @Query("""
            select s from SwapEntity s
            where s.walletAddress = :walletAddress
              and s.blockTime <= :asOf
            order by s.blockTime asc
            """)
    List<SwapEntity> findWalletSwapsBefore(@Param("walletAddress") String walletAddress, @Param("asOf") Instant asOf);
}
