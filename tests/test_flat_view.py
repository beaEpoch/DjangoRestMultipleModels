from django.test import override_settings
from django.core.exceptions import ValidationError
from django.conf.urls import url
from django.core.cache import cache
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework import status, filters

from .utils import MultipleModelTestCase
from .models import Play, Poem
from .serializers import PlaySerializer, PoemSerializer
from drf_multiple_model.views import FlatMultipleModelAPIView


factory = APIRequestFactory()


# Regular Views
class BasicFlatView(FlatMultipleModelAPIView):
    querylist = (
        {'queryset': Play.objects.all(), 'serializer_class': PlaySerializer},
        {'queryset': Poem.objects.filter(style="Sonnet"), 'serializer_class': PoemSerializer},
    )


class SortedFlatView(BasicFlatView):
    sorting_field = 'title'


class ReversedFlatView(BasicFlatView):
    sorting_field = '-title'


class NoLabelView(BasicFlatView):
    add_model_type = False


class CustomLabelView(FlatMultipleModelAPIView):
    querylist = (
        {
            'queryset': Play.objects.all(),
            'serializer_class': PlaySerializer,
            'label': 'Drama',
        },
        {
            'queryset': Poem.objects.filter(style="Sonnet"),
            'serializer_class': PoemSerializer,
            'label': 'Poetry',
        },
    )


class DynamicQueryView(FlatMultipleModelAPIView):
    def get_querylist(self):
        title = self.kwargs['play'].replace('-', ' ')

        querylist = (
            {'queryset': Play.objects.filter(title=title), 'serializer_class': PlaySerializer},
            {'queryset': Poem.objects.filter(style="Sonnet"), 'serializer_class': PoemSerializer},
        )

        return querylist


class SearchFilterView(BasicFlatView):
    filter_backends = (filters.SearchFilter,)
    search_fields = ('title',)


# Testing filter_fn
def title_without_letter(queryset, request, *args, **kwargs):
    letter_to_exclude = request.query_params['letter']
    return queryset.exclude(title__icontains=letter_to_exclude)


class FilterFnView(FlatMultipleModelAPIView):
    querylist = (
        {
            'queryset': Play.objects.all(),
            'serializer_class': PlaySerializer,
            'filter_fn': title_without_letter,
        },
        {
            'queryset': Poem.objects.filter(style="Sonnet"),
            'serializer_class': PoemSerializer,
        },
    )


class CachedQueryView(FlatMultipleModelAPIView):
    querylist = (
        {'queryset': Play.objects.all(), 'serializer_class': PlaySerializer},
        {'queryset': Poem.objects.filter(style="Sonnet"), 'serializer_class': PoemSerializer},
    )

    def load_queryset(self, query_data, request, *args, **kwargs):
        queryset = cache.get('{}-queryset'.format(query_data['queryset'].model.__name__))
        if not queryset:
            queryset = query_data['queryset'].all()
            cache.set('{}-queryset'.format(query_data['queryset'].model.__name__), queryset)
        return queryset


# Broken Views
class NoQuerylistView(FlatMultipleModelAPIView):
    pass


class NoQuerysetView(FlatMultipleModelAPIView):
    querylist = [
        {'serializer_class': PlaySerializer},
        {'serializer_class': PoemSerializer},
    ]


class NoSerializerClassView(FlatMultipleModelAPIView):
    querylist = [
        {'queryset': Play.objects.all()},
        {'queryset': Poem.objects.all()},
    ]


class WrongSortFieldView(BasicFlatView):
    sorting_field = 'year'


urlpatterns = [
    url(r'^$', BasicFlatView.as_view()),
]


# TESTS
@override_settings(ROOT_URLCONF=__name__)
class TestMMFlatViews(MultipleModelTestCase):
    maxDiff = None

    def test_post(self):
        """
        POST requests should throw a 405 Error
        """
        view = BasicFlatView.as_view()

        data = {'fake': 'data'}
        request = factory.post('/', data, format='json')

        with self.assertNumQueries(0):
            response = view(request).render()

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data, {"detail": 'Method "POST" not allowed.'})

    def test_put(self):
        """
        PUT requests should throw a 405 Error
        """
        view = BasicFlatView.as_view()

        data = {'fake': 'data'}
        request = factory.put('/', data, format='json')

        with self.assertNumQueries(0):
            response = view(request).render()

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data, {"detail": 'Method "PUT" not allowed.'})

    def test_delete(self):
        """
        DELETE requests should throw a 405 Error
        """
        view = BasicFlatView.as_view()

        request = factory.delete('/')

        with self.assertNumQueries(0):
            response = view(request).render()

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data, {"detail": 'Method "DELETE" not allowed.'})

    def test_no_querylist(self):
        """
        A view with no querylist and no `get_querylist` overwrite should raise
        an assertion error with the appropriate message
        """
        view = NoQuerylistView.as_view()

        request = factory.get('/')

        with self.assertRaises(AssertionError) as error:
            view(request).render()

        self.assertEqual(str(error.exception), (
            'NoQuerylistView should either include a `querylist` attribute, '
            'or override the `get_querylist()` method.'
        ))

    def test_no_queryset(self):
        """
        A querylist with no `queryset` key should raise a ValidationError with the
        appropriate message
        """
        view = NoQuerysetView.as_view()

        request = factory.get('/')

        with self.assertRaises(ValidationError) as error:
            view(request).render()

        self.assertEqual(error.exception.message, (
            'All items in the NoQuerysetView querylist attribute '
            'should contain a `queryset` key'
        ))

    def test_no_serializer_class(self):
        """
        A querylist with no `serializer_class` key should raise a ValidationError with the
        appropriate message
        """
        view = NoSerializerClassView.as_view()

        request = factory.get('/')

        with self.assertRaises(ValidationError) as error:
            view(request).render()

        self.assertEqual(error.exception.message, (
            'All items in the NoSerializerClassView querylist attribute '
            'should contain a `serializer_class` key'
        ))

    def test_basic_flat_view(self):
        """
        The default setting for the `FlatMultipleModelView` should return
        the serialized objects in querylist order
        """
        view = BasicFlatView.as_view()

        request = factory.get('/')
        with self.assertNumQueries(2):
            response = view(request).render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data), 6)
        self.assertEqual(response.data, [
            {'genre': 'Tragedy', 'title': 'Romeo And Juliet', 'year': 1597, 'type': 'Play'},
            {'genre': 'Comedy', 'title': 'A Midsummer Night\'s Dream', 'year': 1600, 'type': 'Play'},
            {'genre': 'Tragedy', 'title': 'Julius Caesar', 'year': 1623, 'type': 'Play'},
            {'genre': 'Comedy', 'title': 'As You Like It', 'year': 1623, 'type': 'Play'},
            {'title': "Shall I compare thee to a summer's day?", 'style': 'Sonnet', 'type': 'Poem'},
            {'title': "As a decrepit father takes delight", 'style': 'Sonnet', 'type': 'Poem'},
        ])

    def test_no_label(self):
        """
        Tests that no label (aka add_model_type = False) just gives the data
        """
        view = NoLabelView.as_view()

        request = factory.get('/')
        with self.assertNumQueries(2):
            response = view(request).render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data), 6)
        self.assertEqual(response.data, [
            {'title': 'Romeo And Juliet', 'genre': 'Tragedy', 'year': 1597},
            {'title': "A Midsummer Night's Dream", 'genre': 'Comedy', 'year': 1600},
            {'title': 'Julius Caesar', 'genre': 'Tragedy', 'year': 1623},
            {'title': 'As You Like It', 'genre': 'Comedy', 'year': 1623},
            {'title': "Shall I compare thee to a summer's day?", 'style': 'Sonnet'},
            {'title': "As a decrepit father takes delight", 'style': 'Sonnet'}
        ])

    def test_new_labels(self):
        """
        Adding the 'label' key to queryList elements should use those labels
        instead of the model names
        """
        view = CustomLabelView.as_view()

        request = factory.get('/')
        with self.assertNumQueries(2):
            response = view(request).render()

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data), 6)
        self.assertEqual(response.data, [
            {'genre': 'Tragedy', 'title': 'Romeo And Juliet', 'year': 1597, 'type': 'Drama'},
            {'genre': 'Comedy', 'title': 'A Midsummer Night\'s Dream', 'year': 1600, 'type': 'Drama'},
            {'genre': 'Tragedy', 'title': 'Julius Caesar', 'year': 1623, 'type': 'Drama'},
            {'genre': 'Comedy', 'title': 'As You Like It', 'year': 1623, 'type': 'Drama'},
            {'title': "Shall I compare thee to a summer's day?", 'style': 'Sonnet', 'type': 'Poetry'},
            {'title': "As a decrepit father takes delight", 'style': 'Sonnet', 'type': 'Poetry'},
        ])

    def test_filter_fn_view(self):
        """
        The filter function is useful if you want to apply filtering to one query
        but not another (unlike adding view level filtering, which will filter all the
        querysets), but that filtering can't be provided at the beginning (for example, it
        needs to access a query_param).  This is testing the filter_fn.
        """

        view = FilterFnView.as_view()

        request = factory.get('/', {'letter': 'o'})

        with self.assertNumQueries(2):
            response = view(request).render()

        # Check that the plays have been filter to remove those with the letter 'o'
        # But the poems haven't been affected
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [
            {'genre': 'Comedy', 'title': 'A Midsummer Night\'s Dream', 'year': 1600, 'type': 'Play'},
            {'genre': 'Tragedy', 'title': 'Julius Caesar', 'year': 1623, 'type': 'Play'},
            {'title': "Shall I compare thee to a summer's day?", 'style': 'Sonnet', 'type': 'Poem'},
            {'title': "As a decrepit father takes delight", 'style': 'Sonnet', 'type': 'Poem'},
        ])

    def test_sorted_flat(self):
        """
        Adding the sorting_field attribute should order the flat items according to whatever field
        """
        view = SortedFlatView.as_view()

        request = factory.get('/')
        with self.assertNumQueries(2):
            response = view(request).render()

        self.assertEqual(len(response.data), 6)
        self.assertEqual(response.data, [
            {'genre': 'Comedy', 'title': 'A Midsummer Night\'s Dream', 'year': 1600, 'type': 'Play'},
            {'genre': 'Comedy', 'title': 'As You Like It', 'year': 1623, 'type': 'Play'},
            {'title': "As a decrepit father takes delight", 'style': 'Sonnet', 'type': 'Poem'},
            {'genre': 'Tragedy', 'title': 'Julius Caesar', 'year': 1623, 'type': 'Play'},
            {'genre': 'Tragedy', 'title': 'Romeo And Juliet', 'year': 1597, 'type': 'Play'},
            {'title': "Shall I compare thee to a summer's day?", 'style': 'Sonnet', 'type': 'Poem'},
        ])

    def test_reverse_sorted(self):
        """
        Adding a '-' to the front of the sorting_field attribute should order the
        flat items in reverse
        """
        view = ReversedFlatView.as_view()

        request = factory.get('/')
        with self.assertNumQueries(2):
            response = view(request).render()

        self.assertEqual(len(response.data), 6)
        self.assertEqual(response.data, [
            {'title': "Shall I compare thee to a summer's day?", 'style': 'Sonnet', 'type': 'Poem'},
            {'genre': 'Tragedy', 'title': 'Romeo And Juliet', 'year': 1597, 'type': 'Play'},
            {'genre': 'Tragedy', 'title': 'Julius Caesar', 'year': 1623, 'type': 'Play'},
            {'title': "As a decrepit father takes delight", 'style': 'Sonnet', 'type': 'Poem'},
            {'genre': 'Comedy', 'title': 'As You Like It', 'year': 1623, 'type': 'Play'},
            {'genre': 'Comedy', 'title': 'A Midsummer Night\'s Dream', 'year': 1600, 'type': 'Play'},
        ])

    def test_ordered_wrong_sorting(self):
        """
        Sorting by a non-shared field should throw a KeyError
        """
        view = WrongSortFieldView.as_view()

        request = factory.get('/')
        self.assertRaises(KeyError, view, request)

    def test_dynamic_querylist(self):
        """
        using get_querylist allows the construction of dynamic queryLists
        """
        view = DynamicQueryView.as_view()

        request = factory.get('/Julius-Caesar')
        with self.assertNumQueries(2):
            response = view(request, play="Julius-Caesar")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data), 3)
        self.assertEqual(response.data, [
            {'title': 'Julius Caesar', 'genre': 'Tragedy', 'year': 1623, 'type': 'Play'},
            {'title': "Shall I compare thee to a summer's day?", 'style': 'Sonnet', 'type': 'Poem'},
            {'title': "As a decrepit father takes delight", 'style': 'Sonnet', 'type': 'Poem'}
        ])

    def test_search_filter_view(self):
        """
        Tests use of built in DRF filtering with FlatMultipleModelAPIView
        """
        view = SearchFilterView.as_view()

        request = factory.get('/', {'search': 'as'})

        with self.assertNumQueries(2):
            response = view(request).render()

        # Check first page of results
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [
            {'title': 'As You Like It', 'genre': 'Comedy', 'year': 1623, 'type': 'Play'},
            {'title': "As a decrepit father takes delight", 'style': 'Sonnet', 'type': 'Poem'},
        ])

    def test_url_endpoint(self):
        """
        DRF 3.3 broke the MultipleModelAPIView with a load_queryset call
        This test is to replicate (and then fix) that problem
        """
        client = APIClient()
        response = client.get('/', format='api')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cached_querylist(self):
        view = CachedQueryView.as_view()

        request = factory.get('/Julius-Caesar')
        with self.assertNumQueries(2):
            response = view(request, play="Julius-Caesar")
        with self.assertNumQueries(0):
            response = view(request, play="Julius-Caesar")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data), 6)
        self.assertEqual(response.data, [
            {'genre': 'Tragedy', 'title': 'Romeo And Juliet', 'year': 1597, 'type': 'Play'},
            {'genre': 'Comedy', 'title': 'A Midsummer Night\'s Dream', 'year': 1600, 'type': 'Play'},
            {'genre': 'Tragedy', 'title': 'Julius Caesar', 'year': 1623, 'type': 'Play'},
            {'genre': 'Comedy', 'title': 'As You Like It', 'year': 1623, 'type': 'Play'},
            {'title': "Shall I compare thee to a summer's day?", 'style': 'Sonnet', 'type': 'Poem'},
            {'title': "As a decrepit father takes delight", 'style': 'Sonnet', 'type': 'Poem'},
        ])
