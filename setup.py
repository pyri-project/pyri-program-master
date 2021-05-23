from setuptools import setup, find_packages, find_namespace_packages

setup(
    name='pyri-program-master',
    version='0.1.0',
    description='PyRI Teach Pendant Program Master',
    author='John Wason',
    author_email='wason@wasontech.com',
    url='http://pyri.tech',
    package_dir={'': 'src'},
    packages=find_namespace_packages(where='src'),
    include_package_data=True,
    package_data = {
        'pyri.program_master': ['*.robdef','*.yml']
    },
    zip_safe=False,
    install_requires=[
        'pyri-common',
        'pyri-device-manager',
        'pyri-sandbox',
        'robotraconteur'
    ],
    tests_require=['pytest','pytest-asyncio'],
    extras_require={
        'test': ['pytest','pytest-asyncio']
    },
    entry_points = {
        'pyri.plugins.robdef': ['pyri-sandbox-robdef=pyri.program_master.robdef:get_robdef_factory'],
        'pyri.plugins.device_type_adapter': ['pyri-device-states-type-adapter = pyri.program_master.device_type_adapter:get_device_type_adapter_factory'],
        'console_scripts': ['pyri-program-master-service = pyri.program_master.__main__:main']
    }
)