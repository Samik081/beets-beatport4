from setuptools import setup

setup(
    name='beets-beatport4',
    version='0.1.0',
    description='Plugin for beets (http://beets.io) to replace stock beatport plugin which is not yet compatible '
                'with Beatport API v4.',
    long_description=open('README.rst').read(),
    author='Szymon "Samik" Tarasiński',
    author_email='st.samik@gmail.com',
    url='https://github.com/Samik081/beets-beatport4',
    download_url='https://github.com/unrblt/beets-bandcamp/archive/v0.1.3.tar.gz',
    license='GPL-2.0',
    platforms='ALL',

    packages=['beetsplug'],

    install_requires=[
        'beets>=1.6.0',
        'requests',
        'confuse'
    ],

    classifiers=[
        'Topic :: Multimedia :: Sound/Audio',
        'Topic :: Multimedia :: Sound/Audio :: Players :: MP3',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
    ],
)