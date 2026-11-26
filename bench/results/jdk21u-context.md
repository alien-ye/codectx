# Context for: Hash table implementation of the map interface allowing null keys

## Map  (class)  src/java.base/share/classes/java/util/Map.java:163
doc: An object that maps keys to values.  A map cannot contain duplicate keys;
each key can map to at most one value.

<p>This interface takes the place of the {@code Dictionary} class, which
was a totally abstract class rather than an interface.

<p>The {@code Map} interface provides three <i>collection views</i>, which
allow a map's contents to be viewed as a set of keys, collection of values,
or set of key-value mappings.  The <i>order</i> of a map is defined as
the order in which the iterators on the map's collection views return their
elements.  Some map implementations, like the {@code TreeMap} class, make
specific guarantees as to their encounter order; others, like the
{@code HashMap} class, do not. Maps with a defined
<a href="SequencedCollection.html#encounter">encounter order</a>
are generally subtypes of the {@link SequencedMap} interface.

<p>Note: great care must be exercised if mutable objects are used as map
keys.  The behavior of a map is not specified if the value of an object is
changed in a manner that affects {@code equals} comparisons while the
object is a key in the map.  A special case of this prohibition is that it
is not permissible for a map to contain itself as a key.  While it is
permissible for a map to contain itself as a value, extreme caution is
advised: the {@code equals} and {@code hashCode} methods are no longer
well defined on such a map.

<p>All general-purpose map implementation classes should provide two
"standard" constructors: a void (no arguments) constructor which creates an
empty map, and a constructor with a single argument of type {@code Map},
which creates a new map with the same key-value mappings as its argument.
In effect, the latter constructor allows the user to copy any map,
producing an equivalent map of the desired class.  There is no way to
enforce this recommendation (as interfaces cannot contain constructors) but
all of the general-purpose map implementations in the JDK comply.

<p>The "destructive" methods contained in this interface, that is, the
methods that modify the map on which they operate, are specified to throw
{@code UnsupportedOperationException} if this map does not support the
operation.  If this is the case, these methods may, but are not required
to, throw an {@code UnsupportedOperationException} if the invocation would
have no effect on the map.  For example, invoking the {@link #putAll(Map)}
method on an unmodifiable map may, but is not required to, throw the
exception if the map whose mappings are to be "superimposed" is empty.

<p>Some map implementations have restrictions on the keys and values they
may contain.  For example, some implementations prohibit null keys and
values, and some have restrictions on the types of their keys.  Attempting
to insert an ineligible key or value throws an unchecked exception,
typically {@code NullPointerException} or {@code ClassCastException}.
Attempting to query the presence of an ineligible key or value may throw an
exception, or it may simply return false; some implementations will exhibit
the former behavior and some will exhibit the latter.  More generally,
attempting an operation on an ineligible key or value whose completion
would not result in the insertion of an ineligible element into the map may
throw an exception or it may succeed, at the option of the implementation.
Such exceptions are marked as "optional" in the specification for this
interface.

<p>Many methods in Collections Framework interfaces are defined
in terms of the {@link Object#equals(Object) equals} method.  For
example, the specification for the {@link #containsKey(Object)
containsKey(Object key)} method says: "returns {@code true} if and
only if this map contains a mapping for a key {@code k} such that
{@code (key==null ? k==null : key.equals(k))}." This specification should
<i>not</i> be construed to imply that invoking {@code Map.containsKey}
with a non-null argument {@code key} will cause {@code key.equals(k)} to
be invoked for any key {@code k}.  Implementations are free to
implement optimizations whereby the {@code equals} invocation is avoided,
for example, by first comparing the hash codes of the two keys.  (The
{@link Object#hashCode()} specification guarantees that two objects with
unequal hash codes cannot be equal.)  More generally, implementations of
the various Collections Framework interfaces are free to take advantage of
the specified behavior of underlying {@link Object} methods wherever the
implementor deems it appropriate.

<p>Some map operations which perform recursive traversal of the map may fail
with an exception for self-referential instances where the map directly or
indirectly contains itself. This includes the {@code clone()},
{@code equals()}, {@code hashCode()} and {@code toString()} methods.
Implementations may optionally handle the self-referential scenario, however
most current implementations do not do so.

<h2><a id="unmodifiable">Unmodifiable Maps</a></h2>
<p>The {@link Map#of() Map.of},
{@link Map#ofEntries(Map.Entry...) Map.ofEntries}, and
{@link Map#copyOf Map.copyOf}
static factory methods provide a convenient way to create unmodifiable maps.
The {@code Map}
instances created by these methods have the following characteristics:

<ul>
<li>They are <a href="Collection.html#unmodifiable"><i>unmodifiable</i></a>. Keys and values
cannot be added, removed, or updated. Calling any mutator method on the Map
will always cause {@code UnsupportedOperationException} to be thrown.
However, if the contained keys or values are themselves mutable, this may cause the
Map to behave inconsistently or its contents to appear to change.
<li>They disallow {@code null} keys and values. Attempts to create them with
{@code null} keys or values result in {@code NullPointerException}.
<li>They are serializable if all keys and values are serializable.
<li>They reject duplicate keys at creation time. Duplicate keys
passed to a static factory method result in {@code IllegalArgumentException}.
<li>The iteration order of mappings is unspecified and is subject to change.
<li>They are <a href="../lang/doc-files/ValueBased.html">value-based</a>.
Programmers should treat instances that are {@linkplain #equals(Object) equal}
as interchangeable and should not use them for synchronization, or
unpredictable behavior may occur. For example, in a future release,
synchronization may fail. Callers should make no assumptions
about the identity of the returned instances. Factories are free to
create new instances or reuse existing ones.
<li>They are serialized as specified on the
<a href="{@docRoot}/serialized-form.html#java.util.CollSer">Serialized Form</a>
page.
</ul>

<p>This interface is a member of the
<a href="{@docRoot}/java.base/java/util/package-summary.html#CollectionsFramework">
Java Collections Framework</a>.

@param <K> the type of keys maintained by this map
@param <V> the type of mapped values

@author  Josh Bloch
@see HashMap
@see TreeMap
@see Hashtable
@see SortedMap
@see Collection
@see Set
@since 1.2
```
public interface Map<K, V> {
    // Query Operations

    /**
     * Returns the number of key-value mappings in this map.  If the
     * map contains more than {@code Integer.MAX_VALUE} elements, returns
     * {@code Integer.MAX_VALUE}.
     *
     * @return the number of key-value mappings in this map
     */
    int size();

    /**
     * Returns {@code true} if this map contains no key-value mappings.
     *
     * @return {@code true} if this map contains no key-value mappings
     */
    boolean isEmpty();

    /**
     * Returns {@code true} if this map contains a mapping for the specified
     * key.  More formally, returns {@code true} if and only if
     * this map contains a mapping for a key {@code k} such that
     * {@code Objects.equals(key, k)}.  (There can be
     * at most one such mapping.)
     *
     * @param key key whose presence in this map is to be tested
     * @return {@code true} if this map contains a mapping for the specified
     *         key
     * @throws ClassCastException if the key is of an inappropriate type for
     *         this map ({@linkplain Collection##optional-restrictions optional})
     * @throws NullPointerException if the specified key is null and this map
     *         does not permit null keys ({@linkplain Collection##optional-restrictions optional})
     */
    boolean containsKey(Object key);

    /**
     * Returns {@code true} if this map maps one or more keys to the
     * specified value.  More formally, returns {@code true} if and only if
     * this map contains at least one mapping to a value {@code v} such that
     * {@code Objects.equals(value, v)}.  This operation
     * will probably require time linear in the map size for most
     * implementations of the {@code Map} interface.
     *
     * @param value value whose presence in this map is to be tested
     * @return {@code true} if this map maps one or more keys to the
     *         specified value
     * @throws ClassCastException if the value is of an inappropriate type for
     *         this map ({@linkplain Collection##optional-restrictions optional})
     * @throws NullPointerException if the specified value is null and this
     *         map does not permit null values ({@linkplain Collection##optional-restrictions optional})
     */
    boolean containsValue(Object value);

    /**
     * Returns the value to which the specified key is mapped,
     * or {@code null} if this map contains no mapping for the key.
     *
     * <p>More formally, if this map contains a mapping from a key
     * {@code k} to a value {@code v} such that
    // ... (1529 more lines truncated)
```

## HashMapTest.suite.Implementation  (class)  test/jdk/java/util/concurrent/tck/HashMapTest.java:46
```
        class Implementation implements MapImplementation {
            public Class<?> klazz() { return HashMap.class; }
            public Map emptyMap() { return new HashMap(); }
            public boolean isConcurrent() { return false; }
            public boolean permitsNullKeys() { return true; }
            public boolean permitsNullValues() { return true; }
            public boolean supportsSetValue() { return true; }
        }
```

## ConcurrentHashMapTest.suite.Implementation  (class)  test/jdk/java/util/concurrent/tck/ConcurrentHashMapTest.java:55
```
        class Implementation implements MapImplementation {
            public Class<?> klazz() { return ConcurrentHashMap.class; }
            public Map emptyMap() { return new ConcurrentHashMap(); }
            public boolean isConcurrent() { return true; }
            public boolean permitsNullKeys() { return false; }
            public boolean permitsNullValues() { return false; }
            public boolean supportsSetValue() { return true; }
        }
```

## LinkedHashMapTest.suite.Implementation  (class)  test/jdk/java/util/concurrent/tck/LinkedHashMapTest.java:46
```
        class Implementation implements MapImplementation {
            public Class<?> klazz() { return LinkedHashMap.class; }
            public Map emptyMap() { return new LinkedHashMap(); }
            public boolean isConcurrent() { return false; }
            public boolean permitsNullKeys() { return true; }
            public boolean permitsNullValues() { return true; }
            public boolean supportsSetValue() { return true; }
        }
```

## HashtableTest.suite.Implementation  (class)  test/jdk/java/util/concurrent/tck/HashtableTest.java:44
```
        class Implementation implements MapImplementation {
            public Class<?> klazz() { return Hashtable.class; }
            public Map emptyMap() { return new Hashtable(); }
            public boolean isConcurrent() { return true; }
            public boolean permitsNullKeys() { return false; }
            public boolean permitsNullValues() { return false; }
            public boolean supportsSetValue() { return true; }
        }
```

