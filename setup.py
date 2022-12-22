from setuptools import setup

setup(
    name='beets-beatport4',
    version='0.2.8',
    description='Plugin for beets (http://beets.io) to replace stock beatport plugin which is not yet compatible '
                'with Beatport API v4.',
    long_description=open('README.rst').read(),
    author='Szymon "Samik" Tarasinski',
    author_email='st.samik@gmail.com',
    url='https://github.com/Samik081/beets-beatport4',
    download_url='https://github.com/Samik081/beets-beatport4/releases/download/v0.2.8/beets-beatport4-0.2.8.tar.gz',
    license='MIT',
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
        'License :: OSI Approved :: MIT License',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
)