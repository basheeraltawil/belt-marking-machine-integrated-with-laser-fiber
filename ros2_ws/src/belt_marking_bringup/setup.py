from glob import glob

from setuptools import find_packages, setup

package_name = 'belt_marking_bringup'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools', 'PyYAML'],
    zip_safe=True,
    maintainer='Basheer Al-Tawil',
    maintainer_email='basheeraltaweel@gmail.com',
    description='Launch files and machine configuration (sim, real, multi-laser).',
    license='MIT',
    tests_require=['pytest'],
    entry_points={'console_scripts': []},
)
