.. image:: http://img.shields.io/pypi/v/beets-beatport4.svg
    :target: https://pypi.python.org/pypi/beets-beatport4

Plugin for `beets <https://github.com/beetbox/beets>`_ to replace stock beatport plugin and use Beatport API v4 as an
autotagger source.

As Beatport had killed their API v3, the stock beatport plugin does not work anymore. It is also currently not possible to request the access to the API "normal" way, so I have found workaround and updated the code to use the new specification.

Installation
------------

Install this plugin with

..

   $ pip install beets-beatport4

and add ``beatport4`` to the ``plugins`` list in your beets config file.

Beatport Authorization (workaround)
-----------------------------------
1. Visit https://api.beatport.com/v4/docs/
2. Open Network tab in your browser and start capturing the traffic
3. Login with your Beatport account
4. Search for the following request: ``https://api.beatport.com/v4/auth/o/token/?code=...``
5. Copy the response (json access token)
6. Paste it to the `beatport_token.json` file next to your ``beets/config.yaml`` (you can check the path by running ``beet config --paths`` command)
7. Add ``beatport4`` plugin to your ``beets/config.yaml`` plugins list

Configuration and Usage
-----------------------
Apart from the authorization part, plugin should work exactly the same way as the stock one, so please refer to the `official documentation <https://beets.readthedocs.io/en/v1.6.0/plugins/index.html#metadata-source-plugin-configuration>`_