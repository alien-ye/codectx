# Context for: Bootstrap and launch a standalone Spring application

## AbstractApplicationLauncher  (class)  integration-test/spring-boot-server-integration-tests/src/intTest/java/org/springframework/boot/context/embedded/AbstractApplicationLauncher.java:30
doc: Base class for launching a Spring Boot application as part of a JUnit test.

@author Andy Wilkinson
```
abstract class AbstractApplicationLauncher implements BeforeEachCallback {

	private final Application application;

	private final File outputLocation;

	private Process process;

	private int httpPort;

	protected AbstractApplicationLauncher(Application application, File outputLocation) {
		this.application = application;
		this.outputLocation = outputLocation;
	}

	@Override
	public void beforeEach(ExtensionContext context) throws Exception {
		if (this.process == null) {
			this.process = startApplication();
		}
	}

	void destroyProcess() {
		if (this.process != null) {
			this.process.destroy();
			try {
				this.process.waitFor();
			}
			catch (InterruptedException ex) {
				Thread.currentThread().interrupt();
			}
		}
		FileSystemUtils.deleteRecursively(this.outputLocation);
	}

	final int getHttpPort() {
		return this.httpPort;
	}

	protected abstract List<String> getArguments(File archive, File serverPortFile);

	protected abstract File getWorkingDirectory();

	protected abstract String getDescription(String packaging);

	private Process startApplication() throws Exception {
		File workingDirectory = getWorkingDirectory();
		File serverPortFile = new File(this.outputLocation, "server.port");
		serverPortFile.delete();
		File archive = new File("build/spring-boot-server-tests-app/build/libs/spring-boot-server-tests-app-"
				+ this.application.getContainer() + "." + this.application.getPackaging());
		List<String> arguments = new ArrayList<>();
		arguments.add(System.getProperty("java.home") + "/bin/java");
		arguments.addAll(getArguments(archive, serverPortFile));
		arguments.add("--server.servlet.register-default-servlet=true");
		ProcessBuilder processBuilder = new ProcessBuilder(StringUtils.toStringArray(arguments));
		if (workingDirectory != null) {
			processBuilder.directory(workingDirectory);
		}
		Process process = processBuilder.start();
    // ... (40 more lines truncated)
```

## ApplicationLauncher.launchApplication  (method)  module/spring-boot-devtools/src/intTest/java/org/springframework/boot/devtools/tests/ApplicationLauncher.java:17
signature: (JvmLauncher javaLauncher, File serverPortFile) -> LaunchedApplication
```
	LaunchedApplication launchApplication(JvmLauncher javaLauncher, File serverPortFile) throws Exception;
```

## ApplicationLauncher.launchApplication  (method)  module/spring-boot-devtools/src/intTest/java/org/springframework/boot/devtools/tests/ApplicationLauncher.java:19
signature: (JvmLauncher jvmLauncher, File serverPortFile, String... additionalArgs) -> LaunchedApplication
```
	LaunchedApplication launchApplication(JvmLauncher jvmLauncher, File serverPortFile, String... additionalArgs)
			throws Exception;
```

## RemoteApplicationLauncher.launchApplication  (method)  module/spring-boot-devtools/src/intTest/java/org/springframework/boot/devtools/tests/RemoteApplicationLauncher.java:35
signature: (JvmLauncher javaLauncher, File serverPortFile) -> LaunchedApplication
```
	@Override
	public LaunchedApplication launchApplication(JvmLauncher javaLauncher, File serverPortFile) throws Exception {
		LaunchedJvm applicationJvm = javaLauncher.launch("app", createApplicationClassPath(),
				"com.example.DevToolsTestApplication", serverPortFile.getAbsolutePath(), "--server.port=0",
				"--spring.devtools.remote.secret=secret");
		int port = awaitServerPort(applicationJvm, serverPortFile);
		BiFunction<Integer, File, Process> remoteRestarter = getRemoteRestarter(javaLauncher);
		return new LaunchedApplication(getDirectories().getRemoteAppDirectory(), applicationJvm.getStandardOut(),
				applicationJvm.getStandardError(), applicationJvm.getProcess(), remoteRestarter.apply(port, null),
				remoteRestarter);
	}
```

## LocalApplicationLauncher.launchApplication  (method)  module/spring-boot-devtools/src/intTest/java/org/springframework/boot/devtools/tests/LocalApplicationLauncher.java:26
signature: (JvmLauncher jvmLauncher, File serverPortFile) -> LaunchedApplication
```
	@Override
	public LaunchedApplication launchApplication(JvmLauncher jvmLauncher, File serverPortFile) throws Exception {
		LaunchedJvm jvm = jvmLauncher.launch("local", createApplicationClassPath(),
				"com.example.DevToolsTestApplication", serverPortFile.getAbsolutePath(), "--server.port=0");
		return new LaunchedApplication(getDirectories().getAppDirectory(), jvm.getStandardOut(), jvm.getStandardError(),
				jvm.getProcess(), null, null);
	}
```

