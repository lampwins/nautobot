# Nautobot v1.1

This document describes all new features and changes in Nautobot 1.1

Users migrating from NetBox to Nautobot should also refer to the ["Migrating from NetBox"](../installation/migrating-from-netbox.md) documentation as well.

## Release Overview

### Added

#### App Defined Navigation [#12](https://github.com/nautobot/nautobot/pull/485)

Applications can now define tabs, groups, items and buttons in the navigation menu. Using navigation objects a developer can add items to any section of the navigation using key names and weight values. Please see [Application Registry](../development/application-registry.md) for more details.

#### GraphQL ORM Functions

Two new [GraphQL utility functions](../plugins/development.md) have been added to allow easy access to the GraphQL system from source code. Both can be accessed by using `from nautobot.core.graphql import execute_saved_query, execute_query`.

1) `execute_query()`: Runs string as a query against GraphQL.
2) `execute_saved_query()`: Execute a saved query from Nautobot database.

#### MySQL Database Support [#17](https://github.com/nautobot/nautobot/issues/17)

MySQL 8.x is now fully supported as a database backend!

The installation and configuration guides have been revised to include MySQL. If you prefer MySQL or it is more easily supported in your environment, configuring Nautobot to use MySQL is as easy as changing value of `ENGINE` in your `DATABASES` setting to point to `django.db.backends.mysql` and installing the MySQL Python driver using `pip3 install nautobot[mysql]`.

A new `NAUTOBOT_DB_ENGINE` environment variable has been added to allow for specifying the desired database engine at runtime without needing to modify your `nautobot_config.py`. Please see the [configuration guide on `DATABASES`](../configuration/required-settings.md#databases) for more details on how to configure Nautobot to use MySQL.

Please see the MySQL setup guides for [Ubuntu](../installation/ubuntu.md#mysql-setup) and [CentOS](../installation/centos.md#mysql-setup) to get started.

#### Read Only Jobs [#200](https://github.com/nautobot/nautobot/issues/200)

Jobs may be optionally marked as read only by setting the `read_only = True` meta attribute. This prevents the job from making any changes to nautobot data and suppresses certain log messages. Read only jobs can be a great way to safely develop new jobs, and for working with reporting use cases. Please see the [Jobs documentation](../additional-features/jobs.md) for more details.

#### Saved GraphQL Queries [#3](https://github.com/nautobot/nautobot/issues/3)

[Saved GraphQL queries](../additional-features/graphql.md#saved-queries) offers a new model where reusable queries can be stored in Nautobot. New views for managing saved queries are available; additionally, the GraphiQL interface has been augmented to allow populating the interface from a saved query, editing and saving new queries.

Saved queries can easily be imported into the GraphiQL interface by using the new navigation tab located on the right side of the navbar. Inside the new tab are also buttons for editing and saving queries directly into Nautobot's databases.

### Changed

### Removed

## v1.1.0 (2021-MM-DD)

### Added

- [#3](https://github.com/nautobot/nautobot/issues/3) - GraphQL queries can now be saved for later execution
- [#17](https://github.com/nautobot/nautobot/issues/17) - MySQL 8.x is now fully supported as a database backend
- [#200](https://github.com/nautobot/nautobot/issues/200) - Jobs can be marked as read-only
- [#485](https://github.com/nautobot/nautobot/pulls/485) - Applications can define navbar properties through `navigation.py`

### Changed

### Fixed

### Removed