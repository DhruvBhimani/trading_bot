package com.solanaquant;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotNull;

class SolanaQuantApplicationTests {

    @Test
    void applicationClassLoads() {
        assertNotNull(SolanaQuantApplication.class);
    }
}
