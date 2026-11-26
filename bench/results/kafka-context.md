# Context for: Public client for publishing records to Kafka topics

## KAFKA_TOPICS  (variable)  docker/test/constants.py:16
```
KAFKA_TOPICS="fixtures/kafka/bin/kafka-topics.sh"
```

## KafkaClientSupplier  (class)  streams/src/main/java/org/apache/kafka/streams/KafkaClientSupplier.java:33
doc: {@code KafkaClientSupplier} can be used to provide custom Kafka clients to a {@link KafkaStreams} instance.

@see KafkaStreams#KafkaStreams(Topology, java.util.Properties, KafkaClientSupplier)
```
@InterfaceAudience.Public
public interface KafkaClientSupplier {
    /**
     * Create an {@link Admin} which is used for internal topic management.
     *
     * @param config Supplied by the {@link java.util.Properties} given to the {@link KafkaStreams}
     * @return an instance of {@link Admin}
     */
    default Admin getAdmin(final Map<String, Object> config) {
        throw new UnsupportedOperationException("Implementations of KafkaClientSupplier should implement the getAdmin() method.");
    }

    /**
     * Create a {@link Producer} which is used to write records to sink topics.
     *
     * @param config {@link StreamsConfig#getProducerConfigs(String) producer config} which is supplied by the
     *               {@link java.util.Properties} given to the {@link KafkaStreams} instance
     * @return an instance of Kafka producer
     */
    Producer<byte[], byte[]> getProducer(final Map<String, Object> config);

    /**
     * Create a {@link Consumer} which is used to read records of source topics.
     *
     * @param config {@link StreamsConfig#getMainConsumerConfigs(String, String, int) consumer config} which is
     *               supplied by the {@link java.util.Properties} given to the {@link KafkaStreams} instance
     * @return an instance of Kafka consumer
     */
    Consumer<byte[], byte[]> getConsumer(final Map<String, Object> config);

    /**
     * Create a {@link Consumer} which is used to read records to restore {@link StateStore}s.
     *
     * @param config {@link StreamsConfig#getRestoreConsumerConfigs(String) restore consumer config} which is supplied
     *               by the {@link java.util.Properties} given to the {@link KafkaStreams}
     * @return an instance of Kafka consumer
     */
    Consumer<byte[], byte[]> getRestoreConsumer(final Map<String, Object> config);

    /**
     * Create a {@link Consumer} which is used to consume records for {@link GlobalKTable}.
     *
     * @param config {@link StreamsConfig#getGlobalConsumerConfigs(String) global consumer config} which is supplied
     *               by the {@link java.util.Properties} given to the {@link KafkaStreams}
     * @return an instance of Kafka consumer
     */
    Consumer<byte[], byte[]> getGlobalConsumer(final Map<String, Object> config);
}
```

## ConnectRecord  (class)  connect/api/src/main/java/org/apache/kafka/connect/connector/ConnectRecord.java:35
doc: <p>
Base class for records containing data to be copied to/from Kafka. This corresponds closely to
Kafka's {@link org.apache.kafka.clients.producer.ProducerRecord ProducerRecord} and {@link org.apache.kafka.clients.consumer.ConsumerRecord ConsumerRecord} classes, and holds the data that may be used by both
sources and sinks (topic, kafkaPartition, key, value, timestamp, headers). Although both implementations include a
notion of offset, it is not included here because they differ in type.
</p>
```
@InterfaceAudience.Public
public abstract class ConnectRecord<R extends ConnectRecord<R>> {
    private final String topic;
    private final Integer kafkaPartition;
    private final Schema keySchema;
    private final Object key;
    private final Schema valueSchema;
    private final Object value;
    private final Long timestamp;
    private final Headers headers;

    public ConnectRecord(String topic, Integer kafkaPartition,
                         Schema keySchema, Object key,
                         Schema valueSchema, Object value,
                         Long timestamp) {
        this(topic, kafkaPartition, keySchema, key, valueSchema, value, timestamp, new ConnectHeaders());
    }

    public ConnectRecord(String topic, Integer kafkaPartition,
                         Schema keySchema, Object key,
                         Schema valueSchema, Object value,
                         Long timestamp, Iterable<Header> headers) {
        this.topic = topic;
        this.kafkaPartition = kafkaPartition;
        this.keySchema = keySchema;
        this.key = key;
        this.valueSchema = valueSchema;
        this.value = value;
        this.timestamp = timestamp;
        if (headers instanceof ConnectHeaders) {
            this.headers = (ConnectHeaders) headers;
        } else {
            this.headers = new ConnectHeaders(headers);
        }
    }

    public String topic() {
        return topic;
    }

    public Integer kafkaPartition() {
        return kafkaPartition;
    }

    public Object key() {
        return key;
    }

    public Schema keySchema() {
        return keySchema;
    }

    public Object value() {
        return value;
    }

    public Schema valueSchema() {
        return valueSchema;
    }

    // ... (90 more lines truncated)
```

## ControllerMetadataMetricsPublisherTest.testMetricsBeforePublishing  (method)  metadata/src/test/java/org/apache/kafka/controller/metrics/ControllerMetadataMetricsPublisherTest.java:70
signature: () -> void
```
    @Test
    public void testMetricsBeforePublishing() {
        try (TestEnv env = new TestEnv()) {
            assertEquals(0, env.metrics.activeBrokerCount());
            assertEquals(0, env.metrics.globalTopicCount());
            assertEquals(0, env.metrics.globalPartitionCount());
            assertEquals(0, env.metrics.offlinePartitionCount());
            assertEquals(0, env.metrics.preferredReplicaImbalanceCount());
            assertEquals(0, env.metrics.metadataErrorCount());
        }
    }
```

## KafkaPublicApiCheckerExtension  (class)  api-checker/gradle-plugins/src/main/java/org/apache/kafka/gradle/KafkaPublicApiCheckerExtension.java:29
doc: Configuration extension for the KafkaPublicApiChecker plugin.
```
public class KafkaPublicApiCheckerExtension {
    private final Property<Boolean> enabled;
    private final Property<Boolean> failOnViolation;
    private final RegularFileProperty javadocJarPath;
    private final ConfigurableFileCollection projectJarFiles;
    private final ConfigurableFileCollection referenceJarFiles;
    private final RegularFileProperty reportFile;

    public KafkaPublicApiCheckerExtension(Project project) {
        this.enabled = project.getObjects().property(Boolean.class);
        this.enabled.convention(true);

        this.failOnViolation = project.getObjects().property(Boolean.class);
        this.failOnViolation.convention(true);

        this.javadocJarPath = project.getObjects().fileProperty();

        this.projectJarFiles = project.getObjects().fileCollection();

        this.referenceJarFiles = project.getObjects().fileCollection();

        this.reportFile = project.getObjects().fileProperty();
        this.reportFile.convention(project.getLayout().getBuildDirectory().file("reports/kafka-public-api-checker.txt"));
    }

    public Property<Boolean> getEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled.set(enabled);
    }

    public Property<Boolean> getFailOnViolation() {
        return failOnViolation;
    }

    public void setFailOnViolation(boolean failOnViolation) {
        this.failOnViolation.set(failOnViolation);
    }

    public RegularFileProperty getJavadocJarPath() {
        return javadocJarPath;
    }

    public void setJavadocJarPath(File javadocJarPath) {
        this.javadocJarPath.set(javadocJarPath);
    }

    public ConfigurableFileCollection getProjectJarFiles() {
        return projectJarFiles;
    }

    /**
     * Jars of sibling Kafka modules this project depends on. Their classes are merged into the
     * scanned surface so cross-module {@code @InterfaceAudience.Public} references resolve, but
     * they don't contribute to this module's own javadoc-consistency or cascade iteration.
     */
    public ConfigurableFileCollection getReferenceJarFiles() {
        return referenceJarFiles;
    // ... (10 more lines truncated)
```

