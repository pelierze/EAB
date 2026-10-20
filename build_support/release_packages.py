"""Build the EAB archive and checksum from a validated frozen build."""
import hashlib
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from .release_assets import validate_package


def create_packages(source, output, version, source_root=None):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)[.-]?\d+)?', version):
        raise ValueError('Invalid release version')
    version = 'v' + version.removeprefix('v')
    source, output = Path(source).resolve(), Path(output).resolve()
    if output == source or output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('Build and release directories must not overlap')
    validate_package(source, source_root, profile='build')
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    # All temporary files belong to this attempt. Existing release artifacts
    # are never silently overwritten, including a previously published version.
    names = ('EAB',)
    for name in names:
        for suffix in ('.zip', '.zip.sha256.txt'):
            if (output / f'{name}-{version}{suffix}').exists():
                raise FileExistsError(output / f'{name}-{version}{suffix}')
    with tempfile.TemporaryDirectory(prefix='.eab-package-', dir=output) as temporary:
        staging = Path(temporary)
        for name in names:
            package = staging / f'{name}-{version}'
            shutil.copytree(source, package)
            validate_package(package, source_root, profile='eab')
            archive = staging / (package.name + '.zip')
            with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                for path in sorted(package.rglob('*')):
                    if path.is_file():
                        z.write(path, path.relative_to(staging).as_posix())
            with archive.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            checksum = staging / (archive.name + '.sha256.txt')
            checksum.write_text(f'{digest}  {archive.name}\n', encoding='ascii')
            artifacts.extend((archive, checksum))
        published = []
        try:
            for path in artifacts:
                destination = output / path.name
                # Exclusive creation also protects against simultaneous builds.
                with destination.open('xb') as target:
                    published.append(destination)
                    with path.open('rb') as original:
                        shutil.copyfileobj(original, target)
        except Exception:
            for path in published:
                path.unlink()
            raise
    return published


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    for artifact in create_packages(args.source, args.output, args.version):
        print(artifact)
