import json
from typing import Dict, List
from urllib.parse import urljoin

from django import template
from django.apps import apps
from django.utils.safestring import mark_safe

from django_vite.conf import settings

register = template.Library()


class DjangoViteAssetLoader:
    """
    Class handling Vite asset loading.
    """

    _instance = None

    def __init__(self) -> None:
        raise RuntimeError("Use the instance() method instead.")

    def generate_vite_asset(
        self,
        path: str,
        **kwargs: Dict[str, str],
    ) -> str:
        """
        Generates a <script> tag for this JS/TS asset and a <link> tag for
        all of its CSS dependencies by reading the manifest
        file (for production only).
        In development Vite loads all by itself.

        Arguments:
            path {str} -- Path to a Vite JS/TS asset to include.

        Returns:
            str -- All tags to import this file in your HTML page.

        Keyword Arguments:
            **kwargs {Dict[str, str]} -- Adds new attributes to generated
                script tags.

        Raises:
            RuntimeError: If cannot find the file path in the
                manifest (only in production).

        Returns:
            str -- The <script> tag and all <link> tags to import
                this asset in your page.
        """

        if settings.DJANGO_VITE_DEV_MODE:
            return DjangoViteAssetLoader._generate_script_tag(
                DjangoViteAssetLoader._generate_vite_server_url(path),
                {"type": "module", **kwargs},
            )

        if not self._manifest or path not in self._manifest:
            raise RuntimeError(
                f"Cannot find {path} in Vite manifest "
                f"at {settings.DJANGO_VITE_MANIFEST_PATH}"
            )

        tags = []
        manifest_entry = self._manifest[path]
        scripts_attrs = {"type": "module", "crossorigin": "", **kwargs}

        # Add dependent CSS
        tags.extend(self._generate_css_files_of_asset(path, []))

        # Add the script by itself
        tags.append(
            DjangoViteAssetLoader._generate_script_tag(
                DjangoViteAssetLoader._generate_production_server_url(
                    manifest_entry["file"]
                ),
                attrs=scripts_attrs,
            )
        )

        return "\n".join(tags)

    def _generate_css_files_of_asset(
        self, path: str, already_processed: List[str]
    ) -> List[str]:
        """
        Generates all CSS tags for dependencies of an asset.

        Arguments:
            path {str} -- Path to an asset in the 'manifest.json'.
            already_processed {list} -- List of already processed CSS file.

        Returns:
            list -- List of CSS tags.
        """

        tags = []
        manifest_entry = self._manifest[path]

        if "imports" in manifest_entry:
            for import_path in manifest_entry["imports"]:
                tags.extend(
                    self._generate_css_files_of_asset(import_path, already_processed)
                )

        if "css" in manifest_entry:
            for css_path in manifest_entry["css"]:
                if css_path not in already_processed:
                    url = DjangoViteAssetLoader._generate_production_server_url(
                        css_path
                    )
                    tags.append(DjangoViteAssetLoader._generate_stylesheet_tag(url))

                already_processed.append(css_path)

        return tags

    def generate_vite_asset_url(self, path: str) -> str:
        """
        Generates only the URL of an asset managed by ViteJS.
        Warning, this function does not generate URLs for dependant assets.

        Arguments:
            path {str} -- Path to a Vite asset.

        Raises:
            RuntimeError: If cannot find the asset path in the
                manifest (only in production).

        Returns:
            str -- The URL of this asset.
        """

        if settings.DJANGO_VITE_DEV_MODE:
            return DjangoViteAssetLoader._generate_vite_server_url(path)

        if not self._manifest or path not in self._manifest:
            raise RuntimeError(
                f"Cannot find {path} in Vite manifest "
                f"at {settings.DJANGO_VITE_MANIFEST_PATH}"
            )

        return DjangoViteAssetLoader._generate_production_server_url(
            self._manifest[path]["file"]
        )

    def generate_vite_legacy_polyfills(
        self,
        **kwargs: Dict[str, str],
    ) -> str:
        """
        Generates a <script> tag to the polyfills
        generated by '@vitejs/plugin-legacy' if used.
        This tag must be included at end of the <body> before
        including other legacy scripts.

        Keyword Arguments:
            **kwargs {Dict[str, str]} -- Adds new attributes to generated
                script tags.

        Raises:
            RuntimeError: If polyfills path not found inside
                the 'manifest.json' (only in production).

        Returns:
            str -- The script tag to the polyfills.
        """

        if settings.DJANGO_VITE_DEV_MODE:
            return ""

        scripts_attrs = {"nomodule": "", "crossorigin": "", **kwargs}

        for path, content in self._manifest.items():
            if settings.DJANGO_VITE_LEGACY_POLYFILLS_MOTIF in path:
                return DjangoViteAssetLoader._generate_script_tag(
                    DjangoViteAssetLoader._generate_production_server_url(
                        content["file"]
                    ),
                    attrs=scripts_attrs,
                )

        raise RuntimeError(
            f"Vite legacy polyfills not found in manifest "
            f"at {settings.DJANGO_VITE_MANIFEST_PATH}"
        )

    def generate_vite_legacy_asset(
        self,
        path: str,
        **kwargs: Dict[str, str],
    ) -> str:
        """
        Generates a <script> tag for legacy assets JS/TS
        generated by '@vitejs/plugin-legacy'
        (in production only, in development do nothing).

        Arguments:
            path {str} -- Path to a Vite asset to include
                (must contains '-legacy' in its name).

        Keyword Arguments:
            **kwargs {Dict[str, str]} -- Adds new attributes to generated
                script tags.

        Raises:
            RuntimeError: If cannot find the asset path in the
                manifest (only in production).

        Returns:
            str -- The script tag of this legacy asset .
        """

        if settings.DJANGO_VITE_DEV_MODE:
            return ""

        if not self._manifest or path not in self._manifest:
            raise RuntimeError(
                f"Cannot find {path} in Vite manifest "
                f"at {settings.DJANGO_VITE_MANIFEST_PATH}"
            )

        manifest_entry = self._manifest[path]
        scripts_attrs = {"nomodule": "", "crossorigin": "", **kwargs}

        return DjangoViteAssetLoader._generate_script_tag(
            DjangoViteAssetLoader._generate_production_server_url(
                manifest_entry["file"]
            ),
            attrs=scripts_attrs,
        )

    def _parse_manifest(self) -> None:
        """
        Read and parse the Vite manifest file.

        Raises:
            RuntimeError: if cannot load the file or JSON in file is malformed.
        """

        try:
            with open(settings.DJANGO_VITE_MANIFEST_PATH, "r") as manifest_file:
                manifest_content = manifest_file.read()
            self._manifest = json.loads(manifest_content)
        except Exception as error:
            raise RuntimeError(
                f"Cannot read Vite manifest file at "
                f"{settings.DJANGO_VITE_MANIFEST_PATH} : {str(error)}"
            ) from error

    @classmethod
    def instance(cls):
        """
        Singleton.
        Uses singleton to keep parsed manifest in memory after
        the first time it's loaded.

        Returns:
            DjangoViteAssetLoader -- only instance of the class.
        """

        if cls._instance is None:
            cls._instance = cls.__new__(cls)
            cls._instance._manifest = None

            # Manifest is only used in production.
            if not settings.DJANGO_VITE_DEV_MODE:
                cls._instance._parse_manifest()

        return cls._instance

    @classmethod
    def generate_vite_ws_client(cls, **kwargs: Dict[str, str]) -> str:
        """
        Generates the script tag for the Vite WS client for HMR.
        Only used in development, in production this method returns
        an empty string.

        Returns:
            str -- The script tag or an empty string.

        Keyword Arguments:
            **kwargs {Dict[str, str]} -- Adds new attributes to generated
                script tags.
        """

        if not settings.DJANGO_VITE_DEV_MODE:
            return ""

        return cls._generate_script_tag(
            cls._generate_vite_server_url(settings.DJANGO_VITE_WS_CLIENT_URL),
            {"type": "module", **kwargs},
        )

    @staticmethod
    def _generate_script_tag(src: str, attrs: Dict[str, str]) -> str:
        """
        Generates an HTML script tag.

        Arguments:
            src {str} -- Source of the script.

        Keyword Arguments:
            attrs {Dict[str, str]} -- List of custom attributes
                for the tag.

        Returns:
            str -- The script tag.
        """

        attrs_str = " ".join([f'{key}="{value}"' for key, value in attrs.items()])

        return f'<script {attrs_str} src="{src}"></script>'

    @staticmethod
    def _generate_stylesheet_tag(href: str) -> str:
        """
        Generates and HTML <link> stylesheet tag for CSS.

        Arguments:
            href {str} -- CSS file URL.

        Returns:
            str -- CSS link tag.
        """

        return f'<link rel="stylesheet" href="{href}" />'

    @staticmethod
    def _generate_vite_server_url(path: str) -> str:
        """
        Generates an URL to and asset served by the Vite development server.

        Keyword Arguments:
            path {str} -- Path to the asset.

        Returns:
            str -- Full URL to the asset.
        """

        DJANGO_VITE_STATIC_URL = urljoin(
            settings.STATIC_URL, settings.DJANGO_VITE_STATIC_URL_PREFIX
        )

        # Make sure 'DJANGO_VITE_STATIC_URL' finish with a '/'
        if DJANGO_VITE_STATIC_URL[-1] != "/":
            DJANGO_VITE_STATIC_URL += "/"

        return urljoin(
            f"{settings.DJANGO_VITE_DEV_SERVER_PROTOCOL}://"
            f"{settings.DJANGO_VITE_DEV_SERVER_HOST}:{settings.DJANGO_VITE_DEV_SERVER_PORT}",
            urljoin(DJANGO_VITE_STATIC_URL, path),
        )

    @classmethod
    def generate_vite_react_refresh_url(cls) -> str:
        """
        Generates the script for the Vite React Refresh for HMR.
        Only used in development, in production this method returns
        an empty string.

        Returns:
            str -- The script or an empty string.
        """

        if not settings.DJANGO_VITE_DEV_MODE:
            return ""

        return f"""<script type="module">
            import RefreshRuntime from \
            '{cls._generate_vite_server_url(settings.DJANGO_VITE_REACT_REFRESH_URL)}'
            RefreshRuntime.injectIntoGlobalHook(window)
            window.$RefreshReg$ = () => {{}}
            window.$RefreshSig$ = () => (type) => type
            window.__vite_plugin_react_preamble_installed__ = true
        </script>"""

    @staticmethod
    def _generate_production_server_url(path: str) -> str:
        """
        Generates an URL to an asset served during production.

        Keyword Arguments:
            path {str} -- Path to the asset.

        Returns:
            str -- Full URL to the asset.
        """

        if apps.is_installed("django.contrib.staticfiles"):
            from django.contrib.staticfiles.storage import staticfiles_storage

            return staticfiles_storage.url(
                urljoin(settings.DJANGO_VITE_STATIC_URL_PREFIX, path)
            )
        else:
            return urljoin(settings.DJANGO_VITE_STATIC_URL_PREFIX, path)


@register.simple_tag
@mark_safe
def vite_hmr_client(**kwargs: Dict[str, str]) -> str:
    """
    Generates the script tag for the Vite WS client for HMR.
    Only used in development, in production this method returns
    an empty string.

    Returns:
        str -- The script tag or an empty string.

    Keyword Arguments:
        **kwargs {Dict[str, str]} -- Adds new attributes to generated
            script tags.
    """

    return DjangoViteAssetLoader.generate_vite_ws_client(**kwargs)


@register.simple_tag
@mark_safe
def vite_asset(
    path: str,
    **kwargs: Dict[str, str],
) -> str:
    """
    Generates a <script> tag for this JS/TS asset and a <link> tag for
    all of its CSS dependencies by reading the manifest
    file (for production only).
    In development Vite loads all by itself.

    Arguments:
        path {str} -- Path to a Vite JS/TS asset to include.

    Returns:
        str -- All tags to import this file in your HTML page.

    Keyword Arguments:
        **kwargs {Dict[str, str]} -- Adds new attributes to generated
            script tags.

    Raises:
        RuntimeError: If cannot find the file path in the
            manifest (only in production).

    Returns:
        str -- The <script> tag and all <link> tags to import this
            asset in your page.
    """

    assert path is not None

    return DjangoViteAssetLoader.instance().generate_vite_asset(path, **kwargs)


@register.simple_tag
def vite_asset_url(path: str) -> str:
    """
    Generates only the URL of an asset managed by ViteJS.
    Warning, this function does not generate URLs for dependant assets.

    Arguments:
        path {str} -- Path to a Vite asset.

    Raises:
        RuntimeError: If cannot find the asset path in the
            manifest (only in production).

    Returns:
        str -- The URL of this asset.
    """

    assert path is not None

    return DjangoViteAssetLoader.instance().generate_vite_asset_url(path)


@register.simple_tag
@mark_safe
def vite_legacy_polyfills(**kwargs: Dict[str, str]) -> str:
    """
    Generates a <script> tag to the polyfills generated
    by '@vitejs/plugin-legacy' if used.
    This tag must be included at end of the <body> before including
    other legacy scripts.

    Keyword Arguments:
        **kwargs {Dict[str, str]} -- Adds new attributes to generated
            script tags.

    Raises:
        RuntimeError: If polyfills path not found inside
            the 'manifest.json' (only in production).

    Returns:
        str -- The script tag to the polyfills.
    """

    return DjangoViteAssetLoader.instance().generate_vite_legacy_polyfills(**kwargs)


@register.simple_tag
@mark_safe
def vite_legacy_asset(
    path: str,
    **kwargs: Dict[str, str],
) -> str:
    """
    Generates a <script> tag for legacy assets JS/TS
    generated by '@vitejs/plugin-legacy'
    (in production only, in development do nothing).

    Arguments:
        path {str} -- Path to a Vite asset to include
            (must contains '-legacy' in its name).

    Keyword Arguments:
        **kwargs {Dict[str, str]} -- Adds new attributes to generated
            script tags.

    Raises:
        RuntimeError: If cannot find the asset path in
            the manifest (only in production).

    Returns:
        str -- The script tag of this legacy asset .
    """

    assert path is not None

    return DjangoViteAssetLoader.instance().generate_vite_legacy_asset(path, **kwargs)


@register.simple_tag
@mark_safe
def vite_react_refresh() -> str:
    """
    Generates the script for the Vite React Refresh for HMR.
    Only used in development, in production this method returns
    an empty string.

    Returns:
        str -- The script or an empty string.
    """
    return DjangoViteAssetLoader.generate_vite_react_refresh_url()
