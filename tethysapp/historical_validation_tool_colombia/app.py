from tethys_sdk.base import TethysAppBase, url_map_maker


class HistoricalValidationToolColombia(TethysAppBase):
    """
    Tethys app class for Historical Validation Tool Colombia.
    """

    name = 'Historical Validation Tool Colombia'
    index = 'historical_validation_tool_colombia:home'
    icon = 'historical_validation_tool_colombia/images/icon.gif'
    package = 'historical_validation_tool_colombia'
    root_url = 'historical-validation-tool-colombia'
    color = '#2c3e50'
    description = 'Place a brief description of your app here.'
    tags = ''
    enable_feedback = False
    feedback_emails = []

    def url_maps(self):
        """
        Add controllers
        """
        UrlMap = url_map_maker(self.root_url)

        url_maps = (
            UrlMap(
                name='home',
                url='historical-validation-tool-colombia',
                controller='historical_validation_tool_colombia.controllers.home'
            ),
        )

        return url_maps
