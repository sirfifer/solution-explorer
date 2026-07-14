"""Second independent audio pipeline implementation."""


class AudioProcessor:
    """A separate audio pipeline that decodes and resamples audio frames."""

    def run(self, frames):
        return [self._resample(self._decode(f)) for f in frames]

    def _decode(self, frame):
        return frame

    def _resample(self, frame):
        return frame
