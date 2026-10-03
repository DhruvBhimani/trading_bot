package com.solanaquant.bootstrap;

import com.solanaquant.config.SolanaQuantProperties;
import com.solanaquant.ingestion.SampleDatasetService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupBootstrap implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(StartupBootstrap.class);

    private final SolanaQuantProperties properties;
    private final SampleDatasetService sampleDatasetService;

    public StartupBootstrap(SolanaQuantProperties properties, SampleDatasetService sampleDatasetService) {
        this.properties = properties;
        this.sampleDatasetService = sampleDatasetService;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!properties.bootstrapSampleData()) {
            return;
        }
        log.info("BOOTSTRAP_SAMPLE_DATA enabled — loading sample dataset");
        sampleDatasetService.loadSampleDataset();
    }
}
